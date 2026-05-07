'use client';

import { useEffect, useState } from 'react';
import { Search, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useMemorySearch } from '@/features/memory/hooks/useMemory';
import type { MemorySearchResult } from '@/features/memory/types';

interface MemorySearchBarProps {
  onResults: (results: MemorySearchResult[] | null) => void;
}

const STORAGE_KEY_THRESHOLD = 'axon:memory:threshold';
const STORAGE_KEY_LIMIT = 'axon:memory:limit';

const MemorySearchBar = ({ onResults }: MemorySearchBarProps) => {
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState<number>(5);
  const [threshold, setThreshold] = useState<number>(0.35);
  const searchMutation = useMemorySearch();

  useEffect(() => {
    const storedLimit = Number(localStorage.getItem(STORAGE_KEY_LIMIT));
    if (Number.isFinite(storedLimit) && storedLimit >= 1 && storedLimit <= 20) {
      setLimit(storedLimit);
    }
    const storedThreshold = Number(localStorage.getItem(STORAGE_KEY_THRESHOLD));
    if (Number.isFinite(storedThreshold) && storedThreshold >= 0 && storedThreshold <= 1) {
      setThreshold(storedThreshold);
    }
  }, []);

  const trimmed = query.trim();
  const canSearch = trimmed.length > 0 && !searchMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSearch) return;
    searchMutation.mutate(
      { query: trimmed, limit, threshold },
      { onSuccess: (results) => onResults(results) },
    );
  };

  const handleClear = () => {
    setQuery('');
    onResults(null);
    searchMutation.reset();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className='rounded-xl border border-[#2a2a3d] bg-[#1e1e2e] p-4'
    >
      <div className='flex items-center gap-2'>
        <Search className='h-4 w-4 shrink-0 text-[#6b6b8a]' />
        <input
          type='text'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='Search memories…'
          aria-label='Search memories'
          className='flex-1 bg-transparent text-sm text-[#e4e1ed] placeholder:text-[#6b6b8a] focus:outline-none'
        />
        {query && (
          <button
            type='button'
            onClick={handleClear}
            className='rounded-md p-1 text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
            aria-label='Clear search'
          >
            <X className='h-3.5 w-3.5' />
          </button>
        )}
        <Button
          type='submit'
          disabled={!canSearch}
          className='bg-[#494bd6] text-white hover:bg-[#5b5dd9] disabled:bg-[#2a2a3d] disabled:text-[#6b6b8a]'
        >
          {searchMutation.isPending ? 'Searching…' : 'Search'}
        </Button>
      </div>

      <div className='mt-3 flex flex-wrap items-center gap-4 text-xs text-[#6b6b8a]'>
        <label className='flex items-center gap-2'>
          Threshold: <span className='text-[#e4e1ed]'>{threshold.toFixed(2)}</span>
          <input
            type='range'
            min={0}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => {
              const v = Number(e.target.value);
              setThreshold(v);
              localStorage.setItem(STORAGE_KEY_THRESHOLD, String(v));
            }}
            className='accent-[#494bd6]'
            aria-label='Similarity threshold'
          />
        </label>
        <label className='flex items-center gap-2'>
          Limit:
          <input
            type='number'
            min={1}
            max={20}
            value={limit}
            onChange={(e) => {
              const v = Math.max(1, Math.min(20, Number(e.target.value) || 1));
              setLimit(v);
              localStorage.setItem(STORAGE_KEY_LIMIT, String(v));
            }}
            className='w-14 rounded-md border border-[#2a2a3d] bg-[#13131b] px-2 py-1 text-[#e4e1ed] focus:outline-none focus:ring-1 focus:ring-[#494bd6]'
            aria-label='Result limit'
          />
        </label>
      </div>

      {searchMutation.isError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>
          {searchMutation.error.message}
        </p>
      )}
    </form>
  );
};

export default MemorySearchBar;
