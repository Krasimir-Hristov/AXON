'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Trash2, Music } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDeleteAudio } from '@/features/audio/hooks/useAudio';
import type { AudioEntryOut } from '@/features/audio/types';

interface AudioCardProps {
  entry: AudioEntryOut;
}

const AudioCard = ({ entry }: AudioCardProps) => {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { mutate: deleteEntry, isPending } = useDeleteAudio();

  function handleDeleteClick() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    deleteEntry(entry.id);
  }

  const relativeTime = formatDistanceToNow(new Date(entry.created_at), {
    addSuffix: true,
  });

  return (
    <div className='flex flex-col gap-3 rounded-lg border border-[#2a2a3d] bg-[#1a1a2e] p-4'>
      {/* Header row */}
      <div className='flex items-start justify-between gap-2'>
        <div className='flex min-w-0 items-center gap-2'>
          <Music className='h-4 w-4 shrink-0 text-purple-400' />
          <p
            className='truncate text-sm font-medium text-[#e4e1ed]'
            title={entry.title}
          >
            {entry.title}
          </p>
        </div>
        <Button
          size='icon'
          variant='ghost'
          onClick={handleDeleteClick}
          disabled={isPending}
          aria-label={confirmDelete ? 'Confirm delete' : 'Delete audio'}
          className={
            confirmDelete
              ? 'shrink-0 text-red-400 hover:bg-red-900/30 hover:text-red-300'
              : 'shrink-0 text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
          }
          onBlur={() => setConfirmDelete(false)}
        >
          <Trash2 className='h-4 w-4' />
        </Button>
      </div>

      {/* Audio player */}
      {/* TODO: Add WebVTT captions once transcript generation is implemented. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        controls
        src={entry.signed_url}
        className='w-full rounded'
        preload='none'
        aria-label={`Audio: ${entry.title}`}
      />
      <p className='text-xs text-[#6b6b8a]/60 italic'>Captions unavailable</p>

      {/* Footer */}
      <p className='text-xs text-[#6b6b8a]'>{relativeTime}</p>
    </div>
  );
};

export default AudioCard;
