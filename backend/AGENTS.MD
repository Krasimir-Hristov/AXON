# AXON — Agent Architecture Reference

Детайлно описание на всички агенти, инструменти и тяхното взаимодействие в
LangGraph orchestrator-а на AXON.

---

## Обзор на архитектурата

AXON използва **supervisor pattern** — централен LLM (supervisor) получава всяко съобщение
от потребителя и решава дали да отговори директно или да делегира на специализиран
sub-agent. Sub-агентите никога не комуникират директно помежду си — всичко минава
през supervisor-а.

```
START
  │
  ▼
supervisor ──(transfer_to_memory_agent)──► memory_agent    ──► supervisor ──► END
           ──(transfer_to_youtube_agent)─► youtube_agent   ──► supervisor ──► END
           ──(save_video_transcript)──────► save_transcript ──► supervisor ──► END
           ──(generate_tts)───────────────► generate_tts   ──► supervisor ──► END
           ──(отговаря директно)────────────────────────────────────────────► END
```

Графът се компилира веднъж при стартиране (`orchestrator.py:_build_graph()`) и се
преизползва за всяка заявка.

---

## Файлова структура

```
backend/app/agents/
    state.py                   — AxonState TypedDict (споделено между всички nodes)
    orchestrator.py            — компилира LangGraph графа, дефинира _should_continue
    supervisor.py              — supervisor node + handoff @tool definitions
    subagents/
        memory_agent.py        — memory_agent node
        youtube_agent.py       — youtube_agent node
        youtube_fetcher.py     — fetch video ID, oEmbed, transcript (I/O utility)
        youtube_chunker.py     — split transcript entries → text chunks
        youtube_summarizer.py  — LLM chunk summarization + final summary
backend/app/features/youtube/
    tool.py                    — save_transcript_node + SAVE_TRANSCRIPT_TOOL_NAME
```

---

## AxonState — споделено Graph State

**Файл:** `agents/state.py`

Всички nodes четат и пишат в един `TypedDict`. LangGraph управлява мутациите.

| Поле               | Тип                                          | Описание                                                                                                                                                                                 |
| ------------------ | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `messages`         | `Annotated[list[BaseMessage], add_messages]` | Пълна история на разговора. `add_messages` reducer **добавя** нови съобщения, не презаписва.                                                                                             |
| `user_id`          | `str`                                        | Supabase UUID на потребителя — извлечен от JWT, никога не се доверява на клиента.                                                                                                        |
| `model_id`         | `str`                                        | OpenRouter model ID избран от потребителя за тази заявка.                                                                                                                                |
| `memory_context`   | `list[str]`                                  | Откъси върнати от memory_agent за текущия ход.                                                                                                                                           |
| `memory_threshold` | `float`                                      | Праг за cosine similarity при семантично търсене (default 0.35).                                                                                                                         |
| `memory_limit`     | `int`                                        | Максимален брой резултати от memory search (default 5).                                                                                                                                  |
| `youtube_context`  | `str`                                        | JSON payload от youtube_agent (video_id, url, title, channel, duration_s, summary, key_points). Пустo string ако няма видео. **Персистира в DB между ходовете** за cross-turn save flow. |
| `pending_audio`    | `str`                                        | JSON string `{filename, signed_url, text_preview}` от generate_tts_node. Пазен за Phase 10D cross-turn save на аудио файла. Празен string по подразбиране.                               |

---

## Supervisor

**Файл:** `agents/supervisor.py`

### Роля

Supervisor-ът е **единственият entry point** за всяка заявка. Той:

1. Получава цялата история на разговора + системен промпт
2. Решава дали да отговори директно или да извика handoff tool
3. На втория пас (след sub-agent) генерира финалния отговор за потребителя

### Handoff Tools (stub functions)

Supervisor-ът е bind-нат с три `@tool` функции. **Телата им никога не се изпълняват** —
LangGraph засича tool_call по `name` и маршрутира към съответния node.

| Tool name                   | Constant                    | Маршрутира към         |
| --------------------------- | --------------------------- | ---------------------- |
| `transfer_to_memory_agent`  | `HANDOFF_TOOL_NAME`         | `memory_agent` node    |
| `transfer_to_youtube_agent` | `YOUTUBE_HANDOFF_TOOL_NAME` | `youtube_agent` node   |
| `save_video_transcript`     | `SAVE_TRANSCRIPT_TOOL_NAME` | `save_transcript` node |
| `generate_tts`              | `GENERATE_TTS_TOOL_NAME`    | `generate_tts` node    |

### Model Cache

```python
_model_cache: dict[tuple[str, bool], Runnable]
```

Кешира два варианта на модела за всеки `model_id`:

- **`with_tools=True`** — bind-нат с трите handoff tools. Използва се на **първия пас** (нито един sub-agent не е бягал в текущия ход).
- **`with_tools=False`** — без tools. Използва се на **втория пас** (след sub-agent ToolMessage). Гарантира че supervisor-ът никога не ре-делегира в цикъл.

### Ключова логика в `supervisor_node`

**1. Определя дали вече е бягал sub-agent в текущия ход:**

```
last_human_idx → current_turn = messages[last_human_idx+1:]
memory_done = any(isinstance(m, ToolMessage) for m in current_turn)
```

Само съобщенията **след** последния `HumanMessage` се проверяват — исторически
`ToolMessage`-и от минали ходове не блокират бъдещи delegations.

**2. YouTube URL fast-path (bypass на LLM):**

```
if not memory_done AND last HumanMessage съдържа YouTube URL:
    → директно emit AIMessage с tool_call за transfer_to_youtube_agent
    → LLM изобщо не се вика
```

Прави YouTube routing детерминистичен и model-agnostic.

**3. Нормален LLM path:**

```
model = _get_model(model_id, with_tools=not memory_done)
response = await model.astream([SystemMessage, *messages])
```

Supervisor стриймва response-а за SSE token streaming към клиента.

### Системен промпт

Дефиниран в `_SUPERVISOR_SYSTEM_PROMPT`. Съдържа:

- **Езикови правила** — винаги отговаря на езика на потребителя (не на езика на контекста)
- **Memory tool правила** — 7 конкретни случая кога ЗАДЪЛЖИТЕЛНО се вика `transfer_to_memory_agent`; "при съмнение — викай инструмента"
- **YouTube tool правила** — ЗАДЪЛЖИТЕЛНО при YouTube URL; след резултата пита "искаш ли да запазя?"
- **Save правила** — при потвърждение от потребителя + наличен prior summary → вика `save_video_transcript`

---

## memory_agent

**Файл:** `agents/subagents/memory_agent.py`

### Роля

Семантично търсене в дългосрочната памет на потребителя. **Не вика LLM** — само
DB vector search.

### Поток

```
1. Взима last HumanMessage → query string
2. Извлича tool_call_id от последния AIMessage (за да затвори handoff)
3. Вика memory.service.search_memories(user_id, query, threshold, limit)
4. Връща:
   - messages: [ToolMessage(content=snippets_joined, tool_call_id=...)]
   - memory_context: list[str] (индивидуалните snippet-и)
```

**Защо ToolMessage е задължителен:** OpenAI-compatible API-та изискват всяко
`AIMessage` с `tool_calls` да е последвано от `ToolMessage` с matching `tool_call_id`.
Без него следващият LLM call ще върне грешка.

### Interaction с Supervisor

```
Supervisor (pass 1, with_tools=True)
  → AIMessage { tool_calls: [{ name: "transfer_to_memory_agent", id: "abc" }] }

memory_agent_node
  → ToolMessage { tool_call_id: "abc", content: "snippet1\nsnippet2" }
  → state.memory_context = ["snippet1", "snippet2"]

Supervisor (pass 2, with_tools=False)
  → Чете ToolMessage-а от history + memory_context → генерира отговор
  → Не може да ре-делегира (no tools bound)
```

### Грешки

При search failure → `results = []`, supervisor получава "No relevant memories found."
Грешката е логвана, не е re-raise-ната (никога не убива request-а).

---

## youtube_agent

**Файл:** `agents/subagents/youtube_agent.py`

### Роля

Fetch + hierarchical summarization на YouTube видео. Вика LLM за summarization.

### Поток

```
1. Извлича tool_call_id от последния AIMessage
2. Извлича YouTube URL от last HumanMessage → video_id чрез regex
3. asyncio.gather(fetch_transcript(video_id), fetch_oembed(video_id))
4. Изчислява duration_s = last_entry["start"] + last_entry["duration"]
5. build_chunks(transcript_entries) → list[str] чанкове по ~16 000 chars
6. summarize_chunks(chunks) → list[str] паралелно (max 5 concurrent)
7. build_final_summary(chunk_summaries, title, channel) → (summary, key_points)
8. Pydantic validation: YouTubeVideoPayload
9. Връща:
   - messages: [ToolMessage(content=payload_json, tool_call_id=...)]
   - youtube_context: payload_json (string)
```

### Error handling

| Грешка                   | Поведение                                                   |
| ------------------------ | ----------------------------------------------------------- |
| `TranscriptsDisabled`    | ToolMessage с user-friendly съобщение, `youtube_context=""` |
| `NoTranscriptFound`      | ToolMessage с user-friendly съобщение                       |
| `VideoUnavailable`       | ToolMessage с user-friendly съобщение                       |
| All chunk summaries fail | ToolMessage "Failed to summarize..."                        |
| General exception        | Логвано, user-friendly message                              |

### Interaction с Supervisor

```
Supervisor (fast-path, bypass LLM)
  → AIMessage { tool_calls: [{ name: "transfer_to_youtube_agent", id: "xyz" }] }

youtube_agent_node
  → ToolMessage { tool_call_id: "xyz", content: '{"video_id":"...","summary":"..."}' }
  → state.youtube_context = '{"video_id":"...",...}'

Supervisor (pass 2, with_tools=False) [НО сега memory_done=True защото има ToolMessage]
  → Презентира title, channel, duration, summary, key_points на потребителя
  → Пита "Would you like me to save this to your library?"
```

**Забележка:** `youtube_context` се персистира в `conversations.youtube_context` DB
колона от chat service-а — при следващия ход (когато потребителят каже "да, запази")
той е наличен в state въпреки че графът е fresh.

---

## youtube_fetcher (utility, не е node)

**Файл:** `agents/subagents/youtube_fetcher.py`

Три публични функции ползвани от `youtube_agent_node`:

### `extract_video_id(text: str) → str | None`

Regex за YouTube URL-и в следните формати:

- `youtube.com/watch?v=VIDEO_ID`
- `youtube.com/shorts/VIDEO_ID`
- `youtube.com/live/VIDEO_ID`
- `youtube.com/embed/VIDEO_ID`
- `youtu.be/VIDEO_ID`
- С или без `www.`/`m.` prefix, с или без `https://`

### `fetch_oembed(video_id: str) → dict[str, str]`

Вика YouTube oEmbed endpoint (без API ключ). Връща `{title, channel}`.
При грешка → fallback `{"title": "Unknown Title", "channel": "Unknown Channel"}` (non-fatal).

### `fetch_transcript(video_id: str) → list[dict]`

Синхронна `YouTubeTranscriptApi().fetch()` offload-ната в thread pool чрез `asyncio.to_thread`.

- Листва всички налични езици
- Предпочита manual captions пред auto-generated (библиотеката ги връща first)
- Raise-ва `TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable` — хванати от `youtube_agent_node`

---

## youtube_chunker (utility, не е node)

**Файл:** `agents/subagents/youtube_chunker.py`

### `build_chunks(transcript: list[dict]) → list[str]`

Групира transcript entries в текстови чанкове от ~16 000 символа (~4 000 токена, при ~4 chars/token).

```
за всеки entry:
    ако current_chunk + entry > 16 000 chars → flush в chunks, нов chunk
    иначе → добави към current_chunk
```

Мали видеа (<10 мин) → 1 chunk → само едно LLM извикване.
Дълги видеа (>1 час) → много chunks → паралелно summarization.

---

## youtube_summarizer (utility, не е node)

**Файл:** `agents/subagents/youtube_summarizer.py`

### Hierarchical summarization pipeline

**Модел:** `settings.youtube_summary_model` (default: `google/gemini-2.5-flash`) —
non-streaming, висок context window, евтин за summarization.

#### `summarize_chunks(chunks: list[str]) → list[str]`

- `asyncio.Semaphore(5)` — максимум 5 паралелни LLM извиквания едновременно
- Всеки chunk → "Summarize in 3-5 sentences" → chunk summary
- Failed chunks → пропускат се (empty string филтриран)

#### `build_final_summary(chunk_summaries, title, channel) → (summary, key_points)`

- Един LLM call с всички chunk summaries
- Prompt: "Produce a 3-6 sentence summary + list of 5-8 key points. Respond ONLY with valid JSON."
- `_strip_fences()` маха markdown code fences ако моделът ги добавя
- `YouTubeSummaryPayload` Pydantic validation гарантира `{summary: str, key_points: list[str]}`
- При `ValidationError` или `JSONDecodeError` → fallback: `" ".join(chunk_summaries[:3]), []`

### Pydantic Models

**`YouTubeSummaryPayload`** — валидира LLM output:

```python
summary: str
key_points: list[str]  # гарантирано list, не string
```

**`YouTubeVideoPayload`** — валидира целия payload преди записване в state:

```python
video_id, youtube_url, title, channel: str
duration_s: int
summary: str
key_points: list[str]
```

---

## save_transcript (node)

**Файл:** `features/youtube/tool.py`

### Роля

Записва pending YouTube транскрипт в `video_transcripts` таблицата и го индексира
в `memory_entries` (vector DB) за бъдещо семантично извличане.

### Поток

```
1. Извлича tool_call_id от последния AIMessage
2. Чете state["youtube_context"] → parse JSON
3. Валидира задължителни полета: video_id, youtube_url, summary
4. Вика youtube.service.save_transcript(user_id, payload)
5. Връща ToolMessage с confirmation или error string
```

### Interaction с Supervisor

```
Supervisor (pass 1, with_tools=True)
  → Потребителят е казал "да, запази"
  → AIMessage { tool_calls: [{ name: "save_video_transcript", id: "qrs" }] }

save_transcript_node
  → Чете state["youtube_context"] (персистиран от предишния ход)
  → INSERT INTO video_transcripts + INSERT INTO memory_entries
  → ToolMessage { content: "Saved ✓ — **Title** added to library. ID: `uuid`" }

Supervisor (pass 2, with_tools=False)
  → Потвърждава на потребителя
```

### Edge Cases

| Ситуация                         | Поведение                                                             |
| -------------------------------- | --------------------------------------------------------------------- |
| `youtube_context` е empty        | ToolMessage: "No YouTube video data found. Please share a URL first." |
| Invalid JSON в youtube_context   | ToolMessage: "Failed to parse video data — please try again."         |
| Липсват задължителни полета      | ToolMessage: "Video data is incomplete (missing: field1, field2)."    |
| DB save fails                    | ToolMessage: "Failed to save the transcript." (exception logged)      |
| video_id вече съществува за user | Service-ът прави upsert (unique constraint на `(user_id, video_id)`)  |

---

## generate_tts (node)

**Файл:** `features/audio/tool.py`

### Роля

Синтезира текст до реч чрез OpenRouter TTS API, качва MP3 файла в Supabase Storage
и връща signed URL, който supervisor презентира на потребителя като inline audio player.

### Handoff Tool

```python
GENERATE_TTS_TOOL_NAME = "generate_tts"
```

Supervisor е bind-нат с `generate_tts` stub `@tool`. **Тялото никога не се изпълнява** —
LangGraph засича tool_call по `name` и маршрутира към `generate_tts_node`.

### Поток

```
1. Извлича tool_call_id + text arg от последния AIMessage tool_call
2. Валидира: text не е празен
3. Вика audio_service.generate_tts(text, user_id)
   a. mask_pii(text) → masked_text (PII не се изпраща към OpenRouter)
   b. POST {openrouter_base_url}/audio/speech
      body: { model, input: masked_text, voice, response_format: "mp3" }
   c. Валидира отговора: non-empty + Content-Type audio/* или MP3 magic bytes
   d. Returns (mp3_bytes, filename) — filename = "{user_id}/{uuid}.mp3"
4. Вика audio_service.upload_audio(mp3_bytes, filename)
   a. Upload to Supabase Storage "audio" bucket
   b. Creates 7-day signed URL
   c. Returns signed_url
5. Записва { filename, signed_url, text_preview } в state["pending_audio"] (Phase 10D)
6. Връща ToolMessage с markdown [Play audio](signed_url) + save prompt
```

### Interaction с Supervisor

```
Supervisor (pass 1, with_tools=True)
  → Потребителят иска аудио на текст
  → AIMessage { tool_calls: [{ name: "generate_tts", args: { text: "..." }, id: "abc" }] }

generate_tts_node
  → mask_pii → OpenRouter /audio/speech → validate bytes → Supabase Storage upload
  → state["pending_audio"] = '{"filename": "...", "signed_url": "...", "text_preview": "..."}'
  → ToolMessage { content: "Audio generated...\n\n[Play audio](signed_url)\n\nWant me to save?" }

Supervisor (pass 2, with_tools=False)
  → Презентира inline audio link на потребителя
  → Пита дали да запази (Phase 10D)
```

### Frontend интеграция

- `ChatWindow.tsx` — при `tool_use: "Generating audio…"` SSE event → анимиран лилав `Volume2` иконка
- `MessageBubble.tsx` — custom `<a>` renderer: ако `href` завършва с `.mp3` → рендерира `<audio controls src={href}>` inline player вместо обикновен линк

### DeepSeek compatibility fix

DeepSeek и подобни модели понякога emit tool calls като plain text (`generate_tts(text="...")`),
вместо structured `tool_calls`. `supervisor_node` съдържа regex post-processing блок, който
засича такъв формат и го конвертира към структуриран tool_call преди да върне от node-а.
Без тази корекция raw текстът би прокапал към frontend-а.

### Security

- **PII masking:** `mask_pii(text)` се вика преди изпращане към OpenRouter — нито едно PII не напуска системата в plaintext
- **Log hygiene:** `user_id` никога не се логва; само UUID-то на файла се логва при upload; `upload_audio` логва само basename (UUID), не пълния path
- **Response validation:** MP3 magic bytes + Content-Type проверка преди upload — broken response никога не стига до Storage

### Error handling

| Ситуация               | Поведение                                                      |
| ---------------------- | -------------------------------------------------------------- |
| Празен text arg        | ToolMessage с user-friendly съобщение; service не се вика      |
| OpenRouter HTTP грешка | `RuntimeError` с status code; логвано без PII                  |
| Network error          | `RuntimeError`; логвано с URL, без payload                     |
| Invalid audio response | `RuntimeError`; логвано с status/content-type/bytes            |
| Storage upload fails   | `RuntimeError`; exception логвано с UUID само                  |
| Signed URL fails       | `RuntimeError`; exception логвано с UUID само                  |

---

## Orchestrator

**Файл:** `agents/orchestrator.py`

### Роля

Компилира LangGraph `StateGraph` и дефинира routing логиката.

### `_should_continue(state) → str`

Функцията е `conditional_edge` след всяко изпълнение на `supervisor` node.

```python
# 1. Провери дали sub-agent вече е бягал в ТЕКУЩИЯ ход
current_turn = messages[last_human_idx + 1:]
if any(isinstance(m, ToolMessage) for m in current_turn):
    return END  # Supervisor вече е получил резултата → END

# 2. Погледни последния AIMessage за tool_calls
for tc in last.tool_calls:
    if tc["name"] == HANDOFF_TOOL_NAME:        return "memory_agent"
    if tc["name"] == YOUTUBE_HANDOFF_TOOL_NAME: return "youtube_agent"
    if tc["name"] == SAVE_TRANSCRIPT_TOOL_NAME: return "save_transcript"

return END  # Директен отговор
```

**Защо current_turn check:** Без него исторически `ToolMessage`-и от минали ходове
биха казали "sub-agent вече е бягал" и `_should_continue` винаги би върнал `END`,
блокирайки memory/youtube за всеки следващ ход в конверзацията.

### Graph Structure

```python
builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", _should_continue, {...})
builder.add_edge("memory_agent", "supervisor")    # loop back
builder.add_edge("youtube_agent", "supervisor")   # loop back
builder.add_edge("save_transcript", "supervisor") # loop back
builder.add_edge("generate_tts", "supervisor")    # loop back
```

Всеки sub-agent loop-ва обратно към supervisor за финалния response. Ре-delegation
е предотвратена от `with_tools=False` на втория пас.

---

## search_memory @tool (legacy tool, не е в активния граф)

**Файл:** `features/memory/tool.py`

Отделен `@tool` декориран с LangChain's `ToolRuntime` pattern. **Не е свързан
с текущия supervisor граф** — беше ранна имплементация преди supervisor pattern.
`user_id` се чете от `runtime.state` (не от tool args) за сигурност.

Текущата архитектура използва `memory_agent_node` директно, не този tool.

---

## Взаимодействие между компонентите — пълна матрица

| От → До                            | Механизъм                                      | Данни                  |
| ---------------------------------- | ---------------------------------------------- | ---------------------- |
| Chat service → Graph               | `graph.astream_events("v2", initial_state)`    | AxonState              |
| Graph → Supervisor                 | LangGraph `START` edge                         | AxonState              |
| Supervisor → memory_agent          | AIMessage tool_call `transfer_to_memory_agent` | tool_call_id           |
| memory_agent → Supervisor          | ToolMessage + `memory_context` state update    | snippets text          |
| Supervisor → youtube_agent         | AIMessage tool_call (или fast-path bypass)     | tool_call_id           |
| youtube_agent → youtube_fetcher    | директно извикване (не LangGraph)              | video_id               |
| youtube_agent → youtube_chunker    | директно извикване                             | transcript entries     |
| youtube_agent → youtube_summarizer | директно извикване                             | chunks, title, channel |
| youtube_agent → Supervisor         | ToolMessage + `youtube_context` state update   | JSON payload           |
| Supervisor → save_transcript       | AIMessage tool_call `save_video_transcript`    | tool_call_id           |
| save_transcript → youtube.service  | директно извикване                             | payload dict           |
| save_transcript → Supervisor       | ToolMessage с confirmation                     | text                   |
| Supervisor → generate_tts          | AIMessage tool_call `generate_tts`             | tool_call_id + text    |
| generate_tts → audio.service       | директно извикване                             | text, user_id          |
| audio.service → OpenRouter         | `POST /api/v1/audio/speech` (httpx)            | masked text, mp3 bytes |
| audio.service → Supabase Storage   | `storage.upload` + `create_signed_url`         | mp3 bytes, signed URL  |
| generate_tts → Supervisor          | ToolMessage с markdown audio link              | signed URL             |
| Supervisor → Chat service          | `on_chat_model_stream` SSE events              | tokens                 |
| Chat service → DB                  | `update_conversation_youtube_context()`        | youtube_context JSON   |
| Chat service → DB                  | message persistence                            | conversation history   |

---

## Важни дизайнерски решения

### 1. Sub-agents не комуникират директно

Всички sub-agents `→ supervisor → sub-agent` flow. Само supervisor вижда цялата история.
Memory, YouTube и save_transcript не знаят за съществуването си взаимно.

### 2. youtube_context персистира в DB

```
Turn 1: потребителят пита за видео
  → youtube_agent → state["youtube_context"] = JSON
  → chat service finally: UPDATE conversations SET youtube_context = JSON

Turn 2: потребителят казва "да, запази"
  → chat service: initial_state["youtube_context"] = SELECT youtube_context FROM conversations
  → save_transcript_node чете непразен youtube_context → успешен save
```

Без DB persistence `youtube_context` би изчезнал между двата LangGraph invocation-а.

### 3. ToolMessages са задължителни за валидна message history

OpenAI API (и OpenRouter) изискват: след `AIMessage` с `tool_calls` ЗАДЪЛЖИТЕЛНО следват
`ToolMessage`-и с matching `tool_call_id`. Всички sub-agents затварят open tool_call
преди да върнат на supervisor.

### 4. YouTube routing е детерминистичен (LLM bypass)

Supervisor fast-path пропуска LLM call при YouTube URL. Предотвратява случаите
когато моделът се опитва да отговори директно за видеото вместо да извика tool-а.

### 5. Anti-loop: `with_tools=False` на втория пас

Supervisor не може физически да ре-делегира след sub-agent, защото tools са премахнати
от модела. Комбинирано с `_should_continue` current_turn check — двоен guard.
