'use client';

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteAudioEntry,
  listAudioEntries,
  renameAudioEntry,
} from '@/lib/api';
import { createClient } from '@/lib/supabase/client';
import type { AudioEntryOut } from '@/features/audio/types';

// Broad prefix used for mutation invalidation — matches all user variants.
export const AUDIO_ENTRIES_KEY = ['audio-entries'] as const;

function audioEntriesKey(userId: string) {
  return ['audio-entries', userId] as const;
}

function useUserId(): string {
  const [userId, setUserId] = useState('');
  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data }) => setUserId(data.session?.user.id ?? ''));
  }, []);
  return userId;
}

export function useAudioEntries() {
  const userId = useUserId();
  return useQuery<AudioEntryOut[]>({
    queryKey: audioEntriesKey(userId),
    queryFn: listAudioEntries,
    enabled: !!userId,
    staleTime: 60_000,
  });
}

export function useDeleteAudio() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteAudioEntry,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AUDIO_ENTRIES_KEY });
    },
  });
}

export function useRenameAudio() {
  const qc = useQueryClient();
  return useMutation<AudioEntryOut, Error, { id: string; title: string }>({
    mutationFn: ({ id, title }) => renameAudioEntry(id, title),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AUDIO_ENTRIES_KEY });
    },
  });
}
