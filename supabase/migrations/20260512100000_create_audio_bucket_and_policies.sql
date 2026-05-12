-- Phase 10C: Create private 'audio' bucket for TTS mp3 files
-- and RLS policies scoped to {user_id}/ path prefix.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'audio',
  'audio',
  false,                               -- private bucket
  10485760,                            -- 10 MB per file limit
  ARRAY['audio/mpeg', 'audio/mp3']
)
ON CONFLICT (id) DO NOTHING;

-- Allow authenticated users to upload their own files ({user_id}/*)
CREATE POLICY "audio_insert_own"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'audio'
    AND (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- Allow authenticated users to read their own files
CREATE POLICY "audio_select_own"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'audio'
    AND (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- Allow authenticated users to delete their own files (Phase 10D)
CREATE POLICY "audio_delete_own"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'audio'
    AND (storage.foldername(name))[1] = (select auth.uid())::text
  );
