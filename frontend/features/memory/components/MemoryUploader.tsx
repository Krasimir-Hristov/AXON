'use client';

import { useRef, useState } from 'react';
import { Upload, FileCheck2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useUploadMemory } from '@/features/memory/hooks/useMemory';

const ALLOWED_EXTENSIONS = ['.txt', '.md', '.pdf', '.docx'];
const ALLOWED_MIME_TYPES = new Set([
  'text/plain',
  'text/markdown',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);
const MAX_BYTES = 10 * 1024 * 1024; // 10 MB — must match backend limit.

const MemoryUploader = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useUploadMemory();
  const [clientError, setClientError] = useState<string | null>(null);

  const handleFile = (file: File) => {
    if (uploadMutation.isPending) return;
    setClientError(null);
    const lower = file.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setClientError(`Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return;
    }
    if (file.type && !ALLOWED_MIME_TYPES.has(file.type)) {
      setClientError(`Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return;
    }
    if (file.size > MAX_BYTES) {
      setClientError('File exceeds 10 MB limit.');
      return;
    }
    uploadMutation.mutate(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className='rounded-xl border border-dashed border-[#2a2a3d] bg-[#1e1e2e] p-4'
    >
      <input
        ref={inputRef}
        type='file'
        accept={ALLOWED_EXTENSIONS.join(',')}
        onChange={handleChange}
        className='hidden'
        aria-label='Upload memory file'
      />

      <div className='flex items-center justify-between gap-3'>
        <div className='min-w-0 flex-1'>
          <p className='text-xs font-semibold uppercase tracking-widest text-[#6b6b8a]'>
            Upload file
          </p>
          <p className='mt-1 text-xs text-[#6b6b8a]'>
            .txt, .md, .pdf, .docx · max 10 MB
          </p>
        </div>
        <Button
          type='button'
          onClick={() => inputRef.current?.click()}
          disabled={uploadMutation.isPending}
          className='gap-1.5 bg-[#494bd6] text-white hover:bg-[#5b5dd9] disabled:bg-[#2a2a3d] disabled:text-[#6b6b8a]'
        >
          <Upload className='h-4 w-4' />
          {uploadMutation.isPending ? 'Uploading…' : 'Choose file'}
        </Button>
      </div>

      {clientError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>{clientError}</p>
      )}

      {uploadMutation.isError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>
          {uploadMutation.error.message}
        </p>
      )}

      {uploadMutation.isSuccess && uploadMutation.data && (
        <div className='mt-2 inline-flex items-center gap-1.5 rounded-md bg-[#494bd6]/20 px-2 py-1 text-xs text-[#c0c1ff]'>
          <FileCheck2 className='h-3.5 w-3.5' />
          {uploadMutation.data.file_name} · {uploadMutation.data.chunks_created}{' '}
          chunks
        </div>
      )}
    </div>
  );
};

export default MemoryUploader;
