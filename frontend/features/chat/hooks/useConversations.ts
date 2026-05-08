/**
 * TanStack Query hooks for conversation history.
 *
 * - `useConversations` — lists all conversations for the current user
 * - `useConversationMessages` — fetches messages for one conversation
 * - `useDeleteConversation` — deletes a conversation and invalidates the list
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteConversation,
  getConversationMessages,
  listConversations,
} from '@/lib/api';
import type { ConversationOut, MessageOut } from '@/features/chat/types';

export const CONVERSATIONS_KEY = ['chat', 'conversations'] as const;

export function conversationMessagesKey(id: string) {
  return ['chat', 'messages', id] as const;
}

export function useConversations() {
  return useQuery<ConversationOut[], Error>({
    queryKey: CONVERSATIONS_KEY,
    queryFn: listConversations,
    staleTime: 30_000,
  });
}

export function useConversationMessages(id: string | undefined) {
  return useQuery<MessageOut[], Error>({
    queryKey: conversationMessagesKey(id ?? ''),
    queryFn: () => getConversationMessages(id!),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteConversation,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}
