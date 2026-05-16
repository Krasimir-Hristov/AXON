'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteAudioEntry,
  listAudioEntries,
  renameAudioEntry,
} from '@/lib/api';
import type { AudioEntryOut } from '@/features/audio/types';

export const AUDIO_ENTRIES_KEY = ['audio-entries'] as const;

export function useAudioEntries() {
  return useQuery<AudioEntryOut[]>({
    queryKey: AUDIO_ENTRIES_KEY,
    queryFn: listAudioEntries,
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
