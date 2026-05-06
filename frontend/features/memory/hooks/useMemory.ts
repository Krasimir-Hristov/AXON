/**
 * TanStack Query hooks for the Memory feature.
 *
 * - `useMemoryList` — `GET /api/v1/memory`
 * - `useCreateMemory` — `POST /api/v1/memory`
 * - `useDeleteMemory` — `DELETE /api/v1/memory/{id}`
 * - `useMemorySearch` — `POST /api/v1/memory/search` (mutation, on-demand)
 * - `useUploadMemory` — `POST /api/v1/memory/upload` (multipart)
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { z } from 'zod';

import {
  apiFetch,
  apiFetchMultipart,
  apiFetchVoid,
} from '@/lib/api';
import type {
  FileUploadResult,
  MemoryCreatePayload,
  MemoryEntry,
  MemorySearchPayload,
  MemorySearchResult,
} from '@/features/memory/types';

const _createPayloadSchema = z.object({
  content: z.string().min(1).max(20_000),
  metadata: z.record(z.unknown()).optional(),
});

const _searchPayloadSchema = z.object({
  query: z.string().min(1).max(1_000),
  limit: z.number().int().min(1).max(20).optional(),
  threshold: z.number().min(0).max(1).optional(),
});

const MEMORY_LIST_KEY = ['memory', 'list'] as const;

export function useMemoryList() {
  return useQuery<MemoryEntry[], Error>({
    queryKey: MEMORY_LIST_KEY,
    queryFn: () => apiFetch<MemoryEntry[]>('/api/v1/memory'),
    staleTime: 30 * 1000,
  });
}

export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation<MemoryEntry, Error, MemoryCreatePayload>({
    mutationFn: (payload) => {
      _createPayloadSchema.parse(payload);
      return apiFetch<MemoryEntry>('/api/v1/memory', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: MEMORY_LIST_KEY });
    },
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) =>
      apiFetchVoid(`/api/v1/memory/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: MEMORY_LIST_KEY });
    },
  });
}

export function useMemorySearch() {
  return useMutation<MemorySearchResult[], Error, MemorySearchPayload>({
    mutationFn: (payload) => {
      _searchPayloadSchema.parse(payload);
      return apiFetch<MemorySearchResult[]>('/api/v1/memory/search', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
  });
}

export function useUploadMemory() {
  const qc = useQueryClient();
  return useMutation<FileUploadResult, Error, File>({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append('file', file);
      return apiFetchMultipart<FileUploadResult>(
        '/api/v1/memory/upload',
        formData,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: MEMORY_LIST_KEY });
    },
  });
}
