'use client';

import {
  useEffect,
  useRef,
  useState,
  useOptimistic,
  useTransition,
} from 'react';
import { formatDistanceToNow } from 'date-fns';
import { MessageSquarePlus, Trash2, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useQueryClient } from '@tanstack/react-query';
import {
  useConversations,
  useDeleteConversation,
  CONVERSATIONS_KEY,
} from '@/features/chat/hooks/useConversations';
import { updateConversationTitle } from '@/lib/api';
import type { ConversationOut } from '@/features/chat/types';

interface ConversationSidebarProps {
  activeId: string | undefined;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

const SkeletonRow = () => (
  <div className='flex animate-pulse flex-col gap-1.5 rounded-lg px-3 py-2.5'>
    <div className='h-3.5 w-3/4 rounded bg-[#2a2a3d]' />
    <div className='h-2.5 w-1/3 rounded bg-[#22223a]' />
  </div>
);

// ── Single conversation row ───────────────────────────────────────────────────

interface RowProps {
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
}: RowProps) => {
  const [confirming, setConfirming] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newTitle, setNewTitle] = useState(conversation.title);
  const qc = useQueryClient();
  const [optimisticTitle, addOptimisticTitle] = useOptimistic<string, string>(
    conversation.title,
    (_state, updated) => updated,
  );
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const { mutate: deleteConv, isPending: deleteLoading } =
    useDeleteConversation();

  // Auto-cancel confirm state after 3 s of no second click.
  useEffect(() => {
    if (!confirming) return;
    confirmTimerRef.current = setTimeout(() => setConfirming(false), 3000);
    return () => {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    };
  }, [confirming]);

  function handleDeleteClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirming) {
      setConfirming(true);
      return;
    }
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    setConfirming(false);
    deleteConv(conversation.id, {
      onSuccess: () => onDeleted(conversation.id),
    });
  }

  function handleRenameClick(e: React.MouseEvent) {
    e.stopPropagation();
    setRenaming(true);
    setTimeout(() => renameInputRef.current?.focus(), 0);
  }

  async function renameAction(formData: FormData) {
    const title = (formData.get('title') as string).trim();
    if (!title || title === conversation.title) {
      setRenaming(false);
      setNewTitle(conversation.title);
      return;
    }
    addOptimisticTitle(title);
    setRenaming(false);
    try {
      await updateConversationTitle(conversation.id, title);
      // Update the cache so useOptimistic doesn't revert after the transition
      qc.setQueryData<ConversationOut[]>(
        CONVERSATIONS_KEY,
        (prev) =>
          prev?.map((c) => (c.id === conversation.id ? { ...c, title } : c)) ??
          prev,
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

      {/* Action buttons — visible on hover or while confirming */}
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

        {/* Delete button */}
        <button
          type='button'
          aria-label='Delete conversation'
          disabled={deleteLoading}
          onClick={handleDeleteClick}
          className={[
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-all cursor-pointer',
            confirming
              ? 'bg-[#ff4444]/20 text-[#ff4444]'
              : 'text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#ff6b6b]',
            deleteLoading ? 'pointer-events-none opacity-50' : '',
          ].join(' ')}
          title={confirming ? 'Click again to confirm' : 'Delete conversation'}
        >
          <Trash2 className='h-3.5 w-3.5' />
        </button>
      </div>

      {/* Screen-reader live region for confirm state */}
      {confirming && (
        <span className='sr-only' aria-live='polite'>
          Click delete again to confirm removing this conversation.
        </span>
      )}
    </div>
  );
};

// ── Sidebar ───────────────────────────────────────────────────────────────────

const ConversationSidebar = ({
  activeId,
  onSelect,
  onNew,
  onDeleted,
}: ConversationSidebarProps) => {
  const { data: conversations, isLoading } = useConversations();

  return (
    <aside className='flex h-full w-65 shrink-0 flex-col border-r border-[#2a2a3d] bg-[#0f0f17]'>
      {/* New chat */}
      <div className='shrink-0 border-b border-[#2a2a3d] p-3'>
        <Button
          type='button'
          variant='ghost'
          onClick={onNew}
          className='w-full justify-start gap-2 text-[#9b9bb8] hover:bg-[#1e1e2e] hover:text-[#e4e1ed] cursor-pointer'
        >
          <MessageSquarePlus className='h-4 w-4' />
          <span className='text-sm'>New chat</span>
        </Button>
      </div>

      {/* List */}
      <ScrollArea className='flex-1 px-2 py-2'>
        {isLoading ? (
          <div className='space-y-1'>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : !conversations || conversations.length === 0 ? (
          <p className='px-3 py-6 text-center text-xs text-[#6b6b8a]'>
            No conversations yet
          </p>
        ) : (
          <div className='space-y-0.5'>
            {conversations.map((conv) => (
              <ConversationRow
                key={conv.id}
                conversation={conv}
                isActive={conv.id === activeId}
                onSelect={() => onSelect(conv.id)}
                onDeleted={() => onDeleted(conv.id)}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
};

export default ConversationSidebar;
