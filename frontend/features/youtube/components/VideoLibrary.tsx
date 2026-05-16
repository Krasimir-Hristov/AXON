'use client';

import { useVideoTranscripts } from '@/features/youtube/hooks/useYoutube';
import VideoTranscriptCard from '@/features/youtube/components/VideoTranscriptCard';

const SkeletonCard = () => (
  <div className='flex animate-pulse flex-col gap-3 rounded-lg border border-[#2a2a3d] bg-[#1a1a2e] p-4'>
    <div className='h-4 w-3/4 rounded bg-[#2a2a3d]' />
    <div className='h-3 w-1/3 rounded bg-[#2a2a3d]' />
    <div className='h-16 rounded bg-[#2a2a3d]' />
    <div className='h-3 w-1/4 rounded bg-[#2a2a3d]' />
  </div>
);

const VideoLibrary = () => {
  const { data: transcripts, isLoading } = useVideoTranscripts();

  if (isLoading) {
    return (
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {[1, 2, 3].map((i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!transcripts || transcripts.length === 0) {
    return (
      <div className='flex flex-col items-center justify-center py-24 text-center'>
        <p className='text-sm text-[#6b6b8a]'>No saved transcripts yet.</p>
        <p className='mt-1 text-xs text-[#6b6b8a]'>
          Share a YouTube link with AXON to summarize and save it here.
        </p>
      </div>
    );
  }

  return (
    <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
      {transcripts.map((t) => (
        <VideoTranscriptCard key={t.id} transcript={t} />
      ))}
    </div>
  );
};

export default VideoLibrary;
