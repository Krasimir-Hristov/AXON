'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Trash2, Clock, ChevronDown, ChevronUp, Video } from 'lucide-react';
import {
  DialogRoot,
  DialogPopup,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from '@/components/ui/dialog';
import { useDeleteTranscript } from '@/features/youtube/hooks/useYoutube';
import type { VideoTranscriptOut } from '@/features/youtube/types';

interface VideoTranscriptCardProps {
  transcript: VideoTranscriptOut;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0)
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

const VideoTranscriptCard = ({ transcript }: VideoTranscriptCardProps) => {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const { mutate: deleteTranscript, isPending: isDeleting } =
    useDeleteTranscript();

  const displayTitle = transcript.title ?? transcript.video_id;

  function confirmDelete() {
    deleteTranscript(transcript.id, { onSuccess: () => setDeleteOpen(false) });
  }

  const relativeTime = formatDistanceToNow(new Date(transcript.created_at), {
    addSuffix: true,
  });

  return (
    <div className='flex flex-col gap-3 rounded-lg border border-[#2a2a3d] bg-[#1a1a2e] p-4'>
      {/* Header */}
      <div className='flex items-start gap-2'>
        <a
          href={transcript.youtube_url}
          target='_blank'
          rel='noopener noreferrer'
          className='mt-0.5 shrink-0 text-[#6b6b8a] transition-opacity hover:opacity-75'
          aria-label='Open on YouTube'
        >
          <Video className='h-4 w-4' />
        </a>
        <a
          href={transcript.youtube_url}
          target='_blank'
          rel='noopener noreferrer'
          className='min-w-0 flex-1 text-sm font-medium text-[#e4e1ed] hover:underline'
          title={displayTitle}
        >
          <span className='line-clamp-2'>{displayTitle}</span>
        </a>
        <button
          type='button'
          onClick={() => setDeleteOpen(true)}
          disabled={isDeleting}
          aria-label='Delete transcript'
          className='flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-[#ff6b6b] disabled:cursor-not-allowed disabled:opacity-50'
        >
          <Trash2 className='h-4 w-4' />
        </button>
      </div>

      {/* Metadata */}
      {(transcript.channel || transcript.duration_s != null) && (
        <div className='flex items-center gap-3 text-xs text-[#6b6b8a]'>
          {transcript.channel && (
            <span className='truncate'>{transcript.channel}</span>
          )}
          {transcript.duration_s != null && (
            <span className='flex shrink-0 items-center gap-1'>
              <Clock className='h-3 w-3' />
              {formatDuration(transcript.duration_s)}
            </span>
          )}
        </div>
      )}

      {/* Summary */}
      <div>
        <p
          className={`text-xs leading-relaxed text-[#9b9bb8] ${!expanded ? 'line-clamp-3' : ''}`}
        >
          {transcript.summary}
        </p>
        {transcript.summary.length > 160 && (
          <button
            type='button'
            onClick={() => setExpanded(!expanded)}
            className='mt-1 flex items-center gap-0.5 text-xs text-[#6b6b8a] hover:text-[#c0c1ff]'
          >
            {expanded ? (
              <>
                Show less <ChevronUp className='h-3 w-3' />
              </>
            ) : (
              <>
                Show more <ChevronDown className='h-3 w-3' />
              </>
            )}
          </button>
        )}
      </div>

      {/* Key Points */}
      {transcript.key_points.length > 0 && (
        <ul className='flex flex-col gap-1'>
          {transcript.key_points
            .slice(0, expanded ? undefined : 3)
            .map((point, i) => (
              <li
                key={i}
                className='flex items-start gap-1.5 text-xs text-[#9b9bb8]'
              >
                <span className='mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#494bd6]' />
                {point}
              </li>
            ))}
          {!expanded && transcript.key_points.length > 3 && (
            <li className='text-xs text-[#6b6b8a]'>
              +{transcript.key_points.length - 3} more
            </li>
          )}
        </ul>
      )}

      {/* Footer */}
      <p className='text-xs text-[#6b6b8a]'>{relativeTime}</p>

      {/* Delete confirmation dialog */}
      <DialogRoot open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogPopup>
          <DialogTitle>Delete transcript?</DialogTitle>
          <DialogDescription>
            This will permanently delete &ldquo;{displayTitle}&rdquo; and its
            cross-indexed memory entry. This action cannot be undone.
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

export default VideoTranscriptCard;
