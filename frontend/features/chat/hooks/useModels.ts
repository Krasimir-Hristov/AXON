import { useQuery } from '@tanstack/react-query';
import { apiFetchPublic } from '@/lib/api';
import type { ChatModel } from '@/features/chat/types';

export function useModels() {
  return useQuery<ChatModel[], Error>({
    queryKey: ['models'],
    queryFn: () => apiFetchPublic<ChatModel[]>('/api/v1/models'),
    staleTime: 5 * 60 * 1000, // 5 minutes — matches backend TTL cache
  });
}
