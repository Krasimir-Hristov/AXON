import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import VideoLibrary from '@/features/youtube/components/VideoLibrary';

const YouTubePage = () => {
  return (
    <div className='min-h-screen bg-[#13131b] px-4 py-8'>
      <div className='mx-auto max-w-5xl'>
        <div className='mb-6 flex items-center gap-3'>
          <Link
            href='/chat'
            aria-label='Back to chat'
            className='flex h-8 w-8 items-center justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#1e1e2e] hover:text-[#e4e1ed]'
          >
            <ArrowLeft className='h-5 w-5' />
          </Link>
          <h1 className='text-xl font-semibold text-[#e4e1ed]'>
            YouTube Transcripts
          </h1>
        </div>
        <VideoLibrary />
      </div>
    </div>
  );
};

export default YouTubePage;
