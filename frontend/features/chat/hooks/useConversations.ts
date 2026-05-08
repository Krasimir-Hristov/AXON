/**
 * TanStack Query hooks for conversation history.
 *
 * - `useConversations` — lists all conversations for the current user
 * - `useConversationMessages` — fetches messages for one conversation
 * - `useDeleteConversation` — deletes a conversation and invalidates the list
 */

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteConversation,
  getConversationMessages,
  listConversations,
} from '@/lib/api';
import { createClient } from '@/lib/supabase/client';
import type { ConversationOut, MessageOut } from '@/features/chat/types';

/**
 * Base prefix key — used for prefix-based invalidation so it matches all
 * user-scoped variants without needing to know the current userId.
 */
export const CONVERSATIONS_KEY = ['chat', 'conversations'] as const;

export function conversationsKey(userId: string) {
  return ['chat', 'conversations', userId] as const;
}

export function conversationMessagesKey(userId: string, id: string) {
  return ['chat', 'messages', userId, id] as const;
}

/** Returns the current Supabase user's id, or '' before the session resolves. */
export function useUserId(): string {
  const [userId, setUserId] = useState('');
  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data }) => setUserId(data.session?.user.id ?? ''));
  }, []);
  return userId;
}

export function useConversations() {
  const userId = useUserId();
  return useQuery<ConversationOut[], Error>({
    queryKey: conversationsKey(userId),
    queryFn: listConversations,
    enabled: !!userId,
    staleTime: 30_000,
  });
}

export function useConversationMessages(id: string | undefined) {
  const userId = useUserId();
  return useQuery<MessageOut[], Error>({
    queryKey: conversationMessagesKey(userId, id ?? ''),
    queryFn: () => getConversationMessages(id!),
    enabled: !!userId && !!id,
    staleTime: 30_000,
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteConversation,
    onSuccess: () => {
      // Prefix invalidation — matches all user-scoped conversation keys.
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    },
  });
}
