'use client';

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deleteVideoTranscript, listVideoTranscripts } from '@/lib/api';
import { createClient } from '@/lib/supabase/client';
import type { VideoTranscriptOut } from '@/features/youtube/types';

// Broad prefix for mutation invalidation — matches all user variants.
export const VIDEO_TRANSCRIPTS_KEY = ['video-transcripts'] as const;

function videoTranscriptsKey(userId: string) {
  return ['video-transcripts', userId] as const;
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

export function useVideoTranscripts() {
  const userId = useUserId();
  return useQuery<VideoTranscriptOut[]>({
    queryKey: videoTranscriptsKey(userId),
    queryFn: listVideoTranscripts,
    enabled: !!userId,
    staleTime: 60_000,
  });
}

export function useDeleteTranscript() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteVideoTranscript,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: VIDEO_TRANSCRIPTS_KEY });
    },
  });
}
