-- ─── video_transcripts ────────────────────────────────────────────────────────
-- Stores YouTube video summaries saved by the user via the save_video_transcript
-- LangGraph tool.  The summary is also cross-indexed into memory_entries so the
-- memory_agent can surface it during future RAG recall.
CREATE TABLE public.video_transcripts (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    youtube_url TEXT        NOT NULL,
    video_id    TEXT        NOT NULL,
    title       TEXT,
    channel     TEXT,
    duration_s  INTEGER,
    summary     TEXT        NOT NULL,
    key_points  JSONB       NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A user can only save the same video once.
    CONSTRAINT video_transcripts_user_video_unique UNIQUE (user_id, video_id)
);

-- ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX video_transcripts_user_created_idx
    ON public.video_transcripts (user_id, created_at DESC);

-- ─── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.video_transcripts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "video_transcripts: select own"
    ON public.video_transcripts FOR SELECT TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "video_transcripts: insert own"
    ON public.video_transcripts FOR INSERT TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "video_transcripts: delete own"
    ON public.video_transcripts FOR DELETE TO authenticated
    USING ((select auth.uid()) = user_id);
