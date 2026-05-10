'use client';

import { useState } from 'react';
import { Trash2, FileText, Hash } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DialogRoot,
  DialogPopup,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from '@/components/ui/dialog';
import { useDeleteMemory } from '@/features/memory/hooks/useMemory';
import type { MemoryEntry } from '@/features/memory/types';

interface MemoryItemProps {
  entry: MemoryEntry;
  similarity?: number;
}

const MemoryItem = ({ entry, similarity }: MemoryItemProps) => {
  const deleteMutation = useDeleteMemory();
  const [deleteOpen, setDeleteOpen] = useState(false);

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

  function confirmDelete() {
    deleteMutation.mutate(entry.id, {
      onSuccess: () => setDeleteOpen(false),
    });
  }

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
          onClick={() => setDeleteOpen(true)}
          size='icon'
          variant='ghost'
          disabled={deleteMutation.isPending}
          className='text-[#6b6b8a] opacity-0 hover:bg-[#2a2a3d] hover:text-[#ffb4ab] group-hover:opacity-100 focus-visible:opacity-100 focus:opacity-100 cursor-pointer'
          aria-label='Delete memory'
          title='Delete'
        >
          <Trash2 className='h-4 w-4' />
        </Button>
      </div>

      {deleteMutation.isError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>
          Failed to delete: {deleteMutation.error.message}
        </p>
      )}

      <DialogRoot open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogPopup>
          <DialogTitle>Delete memory?</DialogTitle>
          <DialogDescription>This action cannot be undone.</DialogDescription>
          <div className='mt-5 flex justify-end gap-2'>
            <DialogClose
              render={
                <button
                  type='button'
                  className='rounded-lg px-4 py-2 text-sm text-[#9b9bb8] hover:bg-[#1e1e2e] hover:text-[#e4e1ed] transition-colors cursor-pointer'
                />
              }
            >
              Cancel
            </DialogClose>
            <button
              type='button'
              disabled={deleteMutation.isPending}
              onClick={confirmDelete}
              className='rounded-lg bg-[#ff4444]/10 px-4 py-2 text-sm text-[#ff6b6b] hover:bg-[#ff4444]/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer'
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </DialogPopup>
      </DialogRoot>
    </div>
  );
};

export default MemoryItem;
