'use client';

import { useState } from 'react';
import { Trash2, FileText, Hash } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useDeleteMemory } from '@/features/memory/hooks/useMemory';
import type { MemoryEntry } from '@/features/memory/types';

interface MemoryItemProps {
  entry: MemoryEntry;
  similarity?: number;
}

const MemoryItem = ({ entry, similarity }: MemoryItemProps) => {
  const deleteMutation = useDeleteMemory();
  const [confirming, setConfirming] = useState(false);

  const sourceFile =
    typeof entry.metadata?.source_file === 'string'
      ? entry.metadata.source_file
      : null;
  const chunkIndex =
    typeof entry.metadata?.chunk_index === 'number'
      ? entry.metadata.chunk_index
      : null;
  const totalChunks =
    typeof entry.metadata?.total_chunks === 'number'
      ? entry.metadata.total_chunks
      : null;

  const createdAt = new Date(entry.created_at).toLocaleString();

  const handleDelete = () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    deleteMutation.mutate(entry.id);
  };

  return (
    <div className='group relative rounded-xl border border-[#2a2a3d] bg-[#1e1e2e] p-4 transition-colors hover:border-[#494bd6]/50'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0 flex-1'>
          <p className='whitespace-pre-wrap text-sm text-[#e4e1ed]'>
            {entry.content}
          </p>

          <div className='mt-2 flex flex-wrap items-center gap-2 text-[10px] text-[#6b6b8a]'>
            <span>{createdAt}</span>

            {sourceFile && (
              <span className='inline-flex items-center gap-1 rounded-md bg-[#2a2a3d] px-1.5 py-0.5'>
                <FileText className='h-3 w-3' />
                {sourceFile}
              </span>
            )}

            {chunkIndex !== null && totalChunks !== null && (
              <span className='inline-flex items-center gap-1 rounded-md bg-[#2a2a3d] px-1.5 py-0.5'>
                <Hash className='h-3 w-3' />
                {chunkIndex + 1}/{totalChunks}
              </span>
            )}

            {typeof similarity === 'number' && (
              <span className='inline-flex items-center gap-1 rounded-md bg-[#494bd6]/20 px-1.5 py-0.5 text-[#c0c1ff]'>
                {(similarity * 100).toFixed(1)}% match
              </span>
            )}
          </div>
        </div>

        <Button
          onClick={handleDelete}
          onBlur={() => setConfirming(false)}
          size='icon'
          variant='ghost'
          disabled={deleteMutation.isPending}
          className={
            confirming
              ? 'text-[#ffb4ab] hover:bg-[#ffb4ab]/10'
              : 'text-[#6b6b8a] opacity-0 hover:bg-[#2a2a3d] hover:text-[#ffb4ab] group-hover:opacity-100'
          }
          aria-label={confirming ? 'Confirm delete' : 'Delete memory'}
          title={confirming ? 'Click again to confirm' : 'Delete'}
        >
          <Trash2 className='h-4 w-4' />
        </Button>
      </div>

      {deleteMutation.isError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>
          Failed to delete: {deleteMutation.error.message}
        </p>
      )}
    </div>
  );
};

export default MemoryItem;
