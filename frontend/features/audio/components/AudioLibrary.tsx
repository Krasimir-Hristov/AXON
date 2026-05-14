'use client';

import { useAudioEntries } from '@/features/audio/hooks/useAudio';
import AudioCard from '@/features/audio/components/AudioCard';

function SkeletonCard() {
  return (
    <div className='flex flex-col gap-3 rounded-lg border border-[#2a2a3d] bg-[#1a1a2e] p-4 animate-pulse'>
      <div className='h-4 w-3/4 rounded bg-[#2a2a3d]' />
      <div className='h-10 rounded bg-[#2a2a3d]' />
      <div className='h-3 w-1/4 rounded bg-[#2a2a3d]' />
    </div>
  );
}

export default function AudioLibrary() {
  const { data: entries, isLoading } = useAudioEntries();

  if (isLoading) {
    return (
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {[1, 2, 3].map((i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <div className='flex flex-col items-center justify-center py-24 text-center'>
        <p className='text-sm text-[#6b6b8a]'>No saved audio yet.</p>
        <p className='mt-1 text-xs text-[#6b6b8a]'>
          Ask AXON to generate audio and save it here.
        </p>
      </div>
    );
  }

  return (
    <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
      {entries.map((entry) => (
        <AudioCard key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
