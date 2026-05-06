'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Brain, MessageSquare } from 'lucide-react';

import { ScrollArea } from '@/components/ui/scroll-area';
import { useMemoryList } from '@/features/memory/hooks/useMemory';
import MemoryItem from '@/features/memory/components/MemoryItem';
import MemoryCreateForm from '@/features/memory/components/MemoryCreateForm';
import MemoryUploader from '@/features/memory/components/MemoryUploader';
import MemorySearchBar from '@/features/memory/components/MemorySearchBar';
import type { MemorySearchResult } from '@/features/memory/types';

const MemoryView = () => {
  const { data: entries, isLoading, isError, error } = useMemoryList();
  const [searchResults, setSearchResults] =
    useState<MemorySearchResult[] | null>(null);

  const showingSearch = searchResults !== null;

  return (
    <div className='flex h-full flex-col bg-[#13131b]'>
      {/* Header */}
      <div className='flex shrink-0 items-center justify-between border-b border-[#2a2a3d] px-5 py-3'>
        <div className='flex items-center gap-2.5'>
          <div className='flex h-6 w-6 items-center justify-center rounded-md bg-[#494bd6]/20'>
            <Brain className='h-3.5 w-3.5 text-[#c0c1ff]' />
          </div>
          <span className='text-sm font-semibold text-[#e4e1ed]'>Memory</span>
        </div>

        <Link
          href='/chat'
          className='inline-flex items-center gap-1.5 rounded-lg border border-[#2a2a3d] bg-[#1e1e2e] px-3 py-1.5 text-sm text-[#e4e1ed] transition-colors hover:bg-[#2a2a3d]'
        >
          <MessageSquare className='h-3.5 w-3.5' />
          Chat
        </Link>
      </div>

      {/* Content */}
      <ScrollArea className='flex-1 px-4'>
        <div className='mx-auto max-w-3xl space-y-4 py-6'>
          <MemoryCreateForm />
          <MemoryUploader />
          <MemorySearchBar onResults={setSearchResults} />

          <div className='pt-2'>
            <h2 className='mb-3 text-xs font-semibold uppercase tracking-widest text-[#6b6b8a]'>
              {showingSearch
                ? `Search results (${searchResults.length})`
                : 'All memories'}
            </h2>

            {showingSearch ? (
              searchResults.length === 0 ? (
                <p className='py-8 text-center text-xs text-[#6b6b8a]'>
                  No matching memories. Try lowering the threshold.
                </p>
              ) : (
                <div className='space-y-3'>
                  {searchResults.map((r) => (
                    <MemoryItem
                      key={r.id}
                      entry={r}
                      similarity={r.similarity}
                    />
                  ))}
                </div>
              )
            ) : isLoading ? (
              <p className='py-8 text-center text-xs text-[#6b6b8a]'>
                Loading…
              </p>
            ) : isError ? (
              <p className='py-8 text-center text-xs text-[#ffb4ab]'>
                Failed to load memories: {error.message}
              </p>
            ) : !entries || entries.length === 0 ? (
              <p className='py-8 text-center text-xs text-[#6b6b8a]'>
                No memories yet. Add one above or upload a file.
              </p>
            ) : (
              <div className='space-y-3'>
                {entries.map((entry) => (
                  <MemoryItem key={entry.id} entry={entry} />
                ))}
              </div>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
};

export default MemoryView;
