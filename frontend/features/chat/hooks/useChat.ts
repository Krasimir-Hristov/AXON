import { useState, useRef, useCallback, useEffect } from 'react';
import { streamChat } from '@/lib/api';
import type { Message, SSEEvent } from '@/features/chat/types';

function generateId(): string {
  return crypto.randomUUID();
}

/**
 * Per-assistant-message typing buffer.
 *
 * The network stream may deliver tokens in bursts (OpenRouter often returns
 * many tokens in a single SSE flush). To produce a smooth "typing" animation
 * regardless of upstream burstiness, every incoming token is appended to a
 * `pending` queue and a rAF loop drains characters from `pending` into the
 * rendered `Message.content` at a steady rate.
 */
interface TypingBuffer {
  /** Characters received from the network but not yet revealed in the UI. */
  pending: string;
  /** True once the SSE `done` frame for this message has been received. */
  streamComplete: boolean;
  /** Last animation timestamp (rAF clock) — used to compute delta. */
  lastTick: number;
}

// Reveal rate. Tuned so short replies feel snappy and long replies don't drag.
// Effective rate adapts to backlog: if `pending` is large, drain faster.
const BASE_CHARS_PER_SECOND = 80;
const MAX_CHARS_PER_SECOND = 600;

function computeRate(pendingLength: number, streamComplete: boolean): number {
  // When the network is done, drain quickly so user sees full reply soon.
  if (streamComplete) {
    return Math.max(BASE_CHARS_PER_SECOND, Math.min(MAX_CHARS_PER_SECOND, pendingLength * 8));
  }
  // While streaming, scale rate up gently as backlog grows so we never fall behind.
  const scaled = BASE_CHARS_PER_SECOND + Math.min(pendingLength * 2, 300);
  return Math.min(MAX_CHARS_PER_SECOND, scaled);
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const buffersRef = useRef<Map<string, TypingBuffer>>(new Map());
  const rafRef = useRef<number | null>(null);

  // ── Typing animation loop ──────────────────────────────────────────────
  const tick = useCallback((now: number) => {
    const buffers = buffersRef.current;
    if (buffers.size === 0) {
      rafRef.current = null;
      return;
    }

    const updates: { id: string; reveal: string; finished: boolean }[] = [];

    for (const [id, buf] of buffers.entries()) {
      if (buf.lastTick === 0) buf.lastTick = now;
      const deltaSec = (now - buf.lastTick) / 1000;
      buf.lastTick = now;

      const rate = computeRate(buf.pending.length, buf.streamComplete);
      const charsToReveal = Math.max(1, Math.floor(rate * deltaSec));

      if (buf.pending.length === 0) {
        if (buf.streamComplete) {
          updates.push({ id, reveal: '', finished: true });
          buffers.delete(id);
        }
        continue;
      }

      const reveal = buf.pending.slice(0, charsToReveal);
      buf.pending = buf.pending.slice(charsToReveal);

      const finished = buf.streamComplete && buf.pending.length === 0;
      updates.push({ id, reveal, finished });
      if (finished) buffers.delete(id);
    }

    if (updates.length > 0) {
      setMessages((prev) =>
        prev.map((m) => {
          const u = updates.find((x) => x.id === m.id);
          if (!u) return m;
          return {
            ...m,
            content: m.content + u.reveal,
            isStreaming: !u.finished,
          };
        }),
      );
    }

    if (buffers.size > 0) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      rafRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  const ensureLoop = useCallback(() => {
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [tick]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      buffersRef.current.clear();
      abortRef.current?.abort();
    };
  }, []);

  const sendMessage = useCallback(
    async (content: string, modelId: string) => {
      if (isStreaming || !content.trim()) return;

      setError(null);

      const userMsg: Message = { id: generateId(), role: 'user', content };
      const assistantId = generateId();
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      buffersRef.current.set(assistantId, {
        pending: '',
        streamComplete: false,
        lastTick: 0,
      });

      const controller = new AbortController();
      abortRef.current = controller;

      let resolvedConvId = conversationId;

      try {
        await streamChat(
          { message: content, model_id: modelId, conversation_id: resolvedConvId },
          (event: SSEEvent) => {
            if (event.type === 'start') {
              resolvedConvId = event.content;
              setConversationId(event.content);
            } else if (event.type === 'token') {
              const buf = buffersRef.current.get(assistantId);
              if (buf) {
                buf.pending += event.content;
                ensureLoop();
              }
            } else if (event.type === 'error') {
              buffersRef.current.delete(assistantId);
              setError(event.content);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: event.content, isStreaming: false }
                    : m,
                ),
              );
              setIsStreaming(false);
            } else if (event.type === 'done') {
              const buf = buffersRef.current.get(assistantId);
              if (buf) {
                buf.streamComplete = true;
                ensureLoop();
              } else {
                setIsStreaming(false);
              }
            }
          },
          controller.signal,
        );
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        const msg = err instanceof Error ? err.message : 'Unknown error';
        buffersRef.current.delete(assistantId);
        setError(msg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: 'Error: ' + msg, isStreaming: false }
              : m,
          ),
        );
        setIsStreaming(false);
      } finally {
        abortRef.current = null;
        // NOTE: do not set isStreaming=false here — the typing loop owns it
        // and will flip it once the buffer is fully drained.
      }
    },
    [isStreaming, conversationId, ensureLoop],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    buffersRef.current.clear();
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
    );
    setIsStreaming(false);
  }, []);

  const resetConversation = useCallback(() => {
    setMessages([]);
    setConversationId(undefined);
    setError(null);
    buffersRef.current.clear();
  }, []);

  return {
    messages,
    isStreaming,
    conversationId,
    error,
    sendMessage,
    stopStreaming,
    resetConversation,
  };
}
