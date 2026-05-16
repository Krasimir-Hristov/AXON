'use client';

import { useState, useOptimistic, useTransition } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Trash2, Music, Pencil, Check, X } from 'lucide-react';
import {
  DialogRoot,
  DialogPopup,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from '@/components/ui/dialog';
import {
  useDeleteAudio,
  useRenameAudio,
} from '@/features/audio/hooks/useAudio';
import type { AudioEntryOut } from '@/features/audio/types';

interface AudioCardProps {
  entry: AudioEntryOut;
}

const AudioCard = ({ entry }: AudioCardProps) => {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState('');
  const [, startTransition] = useTransition();
  const [optimisticTitle, applyOptimisticTitle] = useOptimistic(
    entry.title,
    (_: string, newTitle: string) => newTitle,
  );

  const { mutate: deleteEntry, isPending: isDeleting } = useDeleteAudio();
  const { mutateAsync: renameEntry } = useRenameAudio();

  function startEdit() {
    setDraftTitle(entry.title);
    setIsEditing(true);
  }

  function cancelEdit() {
    setIsEditing(false);
  }

  function saveEdit() {
    const trimmed = draftTitle.trim();
    if (!trimmed || trimmed === entry.title) {
      setIsEditing(false);
      return;
    }
    setIsEditing(false);
    startTransition(async () => {
      applyOptimisticTitle(trimmed);
      try {
        await renameEntry({ id: entry.id, title: trimmed });
      } catch {
        // useOptimistic reverts to entry.title after the transition ends
      }
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') saveEdit();
    if (e.key === 'Escape') cancelEdit();
  }

  function confirmDelete() {
    deleteEntry(entry.id, { onSuccess: () => setDeleteOpen(false) });
  }

  const relativeTime = formatDistanceToNow(new Date(entry.created_at), {
    addSuffix: true,
  });

  return (
    <div className='flex flex-col gap-3 rounded-lg border border-[#2a2a3d] bg-[#1a1a2e] p-4'>
      {/* Header row */}
      <div className='flex items-center gap-2'>
        <Music className='h-4 w-4 shrink-0 text-purple-400' />
        {isEditing ? (
          <input
            autoFocus
            maxLength={200}
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label='Edit audio title'
            className='min-w-0 flex-1 rounded border border-[#494bd6] bg-[#13131b] px-2 py-0.5 text-sm text-[#e4e1ed] outline-none'
          />
        ) : (
          <p
            className='min-w-0 flex-1 truncate text-sm font-medium text-[#e4e1ed]'
            title={optimisticTitle}
          >
            {optimisticTitle}
          </p>
        )}
        {isEditing ? (
          <div className='flex shrink-0 items-center gap-0.5'>
            <button
              type='button'
              onClick={saveEdit}
              aria-label='Save title'
              className='flex h-8 w-8 items-center justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-green-400'
            >
              <Check className='h-3.5 w-3.5' />
            </button>
            <button
              type='button'
              onClick={cancelEdit}
              aria-label='Cancel edit'
              className='flex h-8 w-8 items-center justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
            >
              <X className='h-3.5 w-3.5' />
            </button>
          </div>
        ) : (
          <div className='flex shrink-0 items-center gap-0.5'>
            <button
              type='button'
              onClick={startEdit}
              aria-label='Edit title'
              className='flex h-8 w-8 items-center cursor-pointer justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-[#c0c1ff]'
            >
              <Pencil className='h-3.5 w-3.5' />
            </button>
            <button
              type='button'
              onClick={() => setDeleteOpen(true)}
              disabled={isDeleting}
              aria-label='Delete audio'
              className='flex h-8 w-8 items-center cursor-pointer justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-[#ff6b6b] disabled:cursor-not-allowed disabled:opacity-50'
            >
              <Trash2 className='h-4 w-4' />
            </button>
          </div>
        )}
      </div>

      {/* Audio player */}
      {/* TODO: Add WebVTT captions once transcript generation is implemented. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        controls
        src={entry.signed_url}
        className='w-full rounded'
        preload='none'
        aria-label={`Audio: ${optimisticTitle}`}
      />
      <p className='text-xs text-[#6b6b8a]/60 italic'>Captions unavailable</p>

      {/* Footer */}
      <p className='text-xs text-[#6b6b8a]'>{relativeTime}</p>

      {/* Delete confirmation dialog */}
      <DialogRoot open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogPopup>
          <DialogTitle>Delete audio?</DialogTitle>
          <DialogDescription>
            This will permanently delete &ldquo;{optimisticTitle}&rdquo; from
            your library and remove the file from storage. This action cannot be
            undone.
          </DialogDescription>
          <div className='mt-5 flex justify-end gap-2'>
            <DialogClose
              render={
                <button
                  type='button'
                  className='cursor-pointer rounded-lg px-4 py-2 text-sm text-[#9b9bb8] transition-colors hover:bg-[#1e1e2e] hover:text-[#e4e1ed]'
                />
              }
            >
              Cancel
            </DialogClose>
            <button
              type='button'
              disabled={isDeleting}
              onClick={confirmDelete}
              className='cursor-pointer rounded-lg bg-[#ff4444]/10 px-4 py-2 text-sm text-[#ff6b6b] transition-colors hover:bg-[#ff4444]/20 disabled:cursor-not-allowed disabled:opacity-50'
            >
              {isDeleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </DialogPopup>
      </DialogRoot>
    </div>
  );
};

export default AudioCard;
