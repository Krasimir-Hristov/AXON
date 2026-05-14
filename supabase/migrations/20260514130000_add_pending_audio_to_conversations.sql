-- Add pending_audio column to conversations for cross-turn save confirmation flow.
-- Mirrors the youtube_context column pattern: persists the JSON payload
-- {filename, signed_url, text_preview} between HTTP requests so the
-- save_audio_entry_node can read it in a subsequent turn.

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS pending_audio TEXT NOT NULL DEFAULT '';
