CREATE OR REPLACE FUNCTION public.match_memories(
    query_embedding  extensions.vector(1536),
    match_user_id    UUID,
    match_threshold  FLOAT  DEFAULT 0.7,
    match_count      INT    DEFAULT 5
)
RETURNS TABLE (
    id                UUID,
    content_encrypted TEXT,
    content_masked    TEXT,
    metadata          JSONB,
    created_at        TIMESTAMPTZ,
    similarity        FLOAT
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, extensions
AS $$
BEGIN
    RETURN QUERY
    SELECT
        me.id,
        me.content_encrypted,
        me.content_masked,
        me.metadata,
        me.created_at,
        1 - (me.embedding <=> query_embedding) AS similarity
    FROM public.memory_entries me
    WHERE
        me.user_id = match_user_id
        AND 1 - (me.embedding <=> query_embedding) >= match_threshold
    ORDER BY me.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
