-- ─── Enable RLS ───────────────────────────────────────────────────────────────
ALTER TABLE public.conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_entries ENABLE ROW LEVEL SECURITY;

-- ─── conversations policies ───────────────────────────────────────────────────
CREATE POLICY "conversations: select own"
    ON public.conversations FOR SELECT TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "conversations: insert own"
    ON public.conversations FOR INSERT TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "conversations: update own"
    ON public.conversations FOR UPDATE TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "conversations: delete own"
    ON public.conversations FOR DELETE TO authenticated
    USING ((select auth.uid()) = user_id);

-- ─── messages policies ────────────────────────────────────────────────────────
CREATE POLICY "messages: select own"
    ON public.messages FOR SELECT TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "messages: insert own"
    ON public.messages FOR INSERT TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "messages: update own"
    ON public.messages FOR UPDATE TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "messages: delete own"
    ON public.messages FOR DELETE TO authenticated
    USING ((select auth.uid()) = user_id);

-- ─── memory_entries policies ──────────────────────────────────────────────────
CREATE POLICY "memory_entries: select own"
    ON public.memory_entries FOR SELECT TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "memory_entries: insert own"
    ON public.memory_entries FOR INSERT TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "memory_entries: update own"
    ON public.memory_entries FOR UPDATE TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "memory_entries: delete own"
    ON public.memory_entries FOR DELETE TO authenticated
    USING ((select auth.uid()) = user_id);
