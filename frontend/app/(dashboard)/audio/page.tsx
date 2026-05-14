import AudioLibrary from '@/features/audio/components/AudioLibrary';

export default function AudioPage() {
  return (
    <div className='min-h-screen bg-[#13131b] px-4 py-8'>
      <div className='mx-auto max-w-5xl'>
        <h1 className='mb-6 text-xl font-semibold text-[#e4e1ed]'>
          Audio Library
        </h1>
        <AudioLibrary />
      </div>
    </div>
  );
}
