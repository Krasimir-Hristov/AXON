-- user_id indexes (required for RLS performance — prevents full table scans)
CREATE INDEX idx_conversations_user_id    ON public.conversations (user_id);
CREATE INDEX idx_messages_user_id         ON public.messages (user_id);
CREATE INDEX idx_memory_entries_user_id   ON public.memory_entries (user_id);

-- FK index: messages → conversations
CREATE INDEX idx_messages_conversation_id ON public.messages (conversation_id);

-- covering index for ordered message list queries
CREATE INDEX idx_messages_conv_created    ON public.messages (conversation_id, created_at);

-- HNSW index for pgvector cosine similarity search
CREATE INDEX idx_memory_entries_embedding
    ON public.memory_entries
    USING hnsw (embedding extensions.vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
