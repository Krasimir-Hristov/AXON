-- Phase 10D: Audio Library
-- Creates the audio_entries table for saving TTS-generated audio files.

create table if not exists public.audio_entries (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references auth.users(id) on delete cascade,
    filename      text not null,           -- storage path: {user_id}/{uuid}.mp3
    title         text not null,           -- user-facing label
    source_type   text not null default 'custom', -- 'youtube' | 'custom'
    source_id     uuid references public.video_transcripts(id) on delete set null,
    duration_s    integer,                 -- estimated from text length
    created_at    timestamptz not null default now()
);

-- Index for user-scoped listing ordered by newest first.
create index if not exists audio_entries_user_created_idx
    on public.audio_entries (user_id, created_at desc);

-- Index for FK lookups on source_id (prevents full-table scans on video_transcripts delete cascade).
create index if not exists audio_entries_source_id_idx
    on public.audio_entries (source_id);

-- Enable RLS.
alter table public.audio_entries enable row level security;

create policy "Users can select their own audio entries"
    on public.audio_entries for select
    using ((select auth.uid()) = user_id);

create policy "Users can insert their own audio entries"
    on public.audio_entries for insert
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own audio entries"
    on public.audio_entries for delete
    using ((select auth.uid()) = user_id);
