'use client';

import { useEffect, useRef, useState, useOptimistic } from 'react';
import { z } from 'zod';
import { formatDistanceToNow } from 'date-fns';
import { Trash2, Edit2 } from 'lucide-react';
import {
  DialogRoot,
  DialogPopup,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from '@/components/ui/dialog';
import { useQueryClient } from '@tanstack/react-query';
import {
  useDeleteConversation,
  useUserId,
  conversationsKey,
} from '@/features/chat/hooks/useConversations';
import { updateConversationTitle } from '@/lib/api';
import type { ConversationOut } from '@/features/chat/types';

const TitleSchema = z.object({
  title: z
    .string()
    .min(1)
    .max(200)
    .transform((s) => s.trim()),
});

export interface ConversationRowProps {
  conversation: ConversationOut;
  isActive: boolean;
  onSelect: () => void;
  onDeleted: (id: string) => void;
}

const ConversationRow = ({
  conversation,
  isActive,
  onSelect,
  onDeleted,
}: ConversationRowProps) => {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newTitle, setNewTitle] = useState(conversation.title);
  const userId = useUserId();
  const qc = useQueryClient();
  const [optimisticTitle, addOptimisticTitle] = useOptimistic<string, string>(
    conversation.title,
    (_state, updated) => updated,
  );

  // Keep the input in sync if the parent data changes (e.g. after a rename).
  useEffect(() => {
    setNewTitle(conversation.title);
  }, [conversation.title]);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const { mutate: deleteConv, isPending: deleteLoading } =
    useDeleteConversation();

  function handleDeleteClick(e: React.MouseEvent) {
    e.stopPropagation();
    setDeleteOpen(true);
  }

  function confirmDelete() {
    deleteConv(conversation.id, {
      onSuccess: () => {
        setDeleteOpen(false);
        onDeleted(conversation.id);
      },
    });
  }

  function handleRenameClick(e: React.MouseEvent) {
    e.stopPropagation();
    setRenaming(true);
    setTimeout(() => renameInputRef.current?.focus(), 0);
  }

  async function renameAction(formData: FormData) {
    const parsed = TitleSchema.safeParse({ title: formData.get('title') });
    if (!parsed.success) {
      setRenaming(false);
      setNewTitle(conversation.title);
      return;
    }
    const { title } = parsed.data;
    if (title === conversation.title) {
      setRenaming(false);
      return;
    }
    addOptimisticTitle(title);
    setRenaming(false);
    try {
      const updated = await updateConversationTitle(conversation.id, title);
      setNewTitle(updated.title);
      // Update the cache so useOptimistic doesn't revert after the transition
      qc.setQueryData<ConversationOut[]>(
        conversationsKey(userId),
        (prev) =>
          prev?.map((c) =>
            c.id === conversation.id ? { ...c, title: updated.title } : c,
          ) ?? prev,
      );
    } catch (err) {
      console.error('Failed to rename conversation:', err);
    }
  }

  function handleRenameCancel() {
    setRenaming(false);
    setNewTitle(conversation.title);
  }

  const relativeTime = (() => {
    try {
      return formatDistanceToNow(new Date(conversation.updated_at), {
        addSuffix: true,
      });
    } catch {
      return '';
    }
  })();

  if (renaming) {
    return (
      <form
        ref={formRef}
        action={renameAction}
        className='group relative flex items-center gap-1 px-2 py-1'
      >
        <input
          ref={renameInputRef}
          name='title'
          type='text'
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') handleRenameCancel();
          }}
          onBlur={() => formRef.current?.requestSubmit()}
          className='flex-1 rounded bg-[#1e1e2e] px-2 py-1 text-xs text-[#e4e1ed] focus:outline-none focus:ring-1 focus:ring-[#494bd6]'
          placeholder='Conversation title...'
        />
      </form>
    );
  }

  return (
    <div className='group relative flex items-center'>
      <button
        type='button'
        aria-current={isActive ? 'page' : undefined}
        onClick={onSelect}
        className={[
          'flex min-w-0 flex-1 flex-col rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer',
          isActive
            ? 'bg-[#494bd6]/20 text-[#e4e1ed]'
            : 'text-[#9b9bb8] hover:bg-[#1e1e2e] hover:text-[#e4e1ed]',
        ].join(' ')}
      >
        <span className='line-clamp-1 text-sm font-medium leading-snug'>
          {optimisticTitle}
        </span>
        <span className='mt-0.5 text-xs text-[#6b6b8a]'>{relativeTime}</span>
      </button>

      {/* Action buttons — visible on hover */}
      <div className='absolute right-1 flex gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-all'>
        {/* Rename button */}
        <button
          type='button'
          aria-label='Rename conversation'
          onClick={handleRenameClick}
          className='flex h-7 w-7 shrink-0 items-center justify-center rounded-md cursor-pointer text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#9b9bb8] transition-colors'
          title='Rename conversation'
        >
          <Edit2 className='h-3.5 w-3.5' />
        </button>

        {/* Delete button — opens confirmation dialog */}
        <button
          type='button'
          aria-label='Delete conversation'
          onClick={handleDeleteClick}
          className='flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-all cursor-pointer text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#ff6b6b]'
          title='Delete conversation'
        >
          <Trash2 className='h-3.5 w-3.5' />
        </button>
      </div>

      {/* Delete confirmation dialog */}
      <DialogRoot open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogPopup>
          <DialogTitle>Delete conversation?</DialogTitle>
          <DialogDescription>
            This will permanently delete &ldquo;{conversation.title}&rdquo;.
            This action cannot be undone.
          </DialogDescription>
          <div className='mt-5 flex justify-end gap-2'>
            <DialogClose
              render={
                <button
                  type='button'
                  className='rounded-lg px-4 py-2 text-sm text-[#9b9bb8] hover:bg-[#1e1e2e] hover:text-[#e4e1ed] transition-colors cursor-pointer'
                />
              }
            >
              Cancel
            </DialogClose>
            <button
              type='button'
              disabled={deleteLoading}
              onClick={confirmDelete}
              className='rounded-lg bg-[#ff4444]/10 px-4 py-2 text-sm text-[#ff6b6b] hover:bg-[#ff4444]/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer'
            >
              {deleteLoading ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </DialogPopup>
      </DialogRoot>
    </div>
  );
};

export default ConversationRow;
