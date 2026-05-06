'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useCreateMemory } from '@/features/memory/hooks/useMemory';

const MAX_LENGTH = 20_000;

const MemoryCreateForm = () => {
  const [content, setContent] = useState('');
  const createMutation = useCreateMemory();

  const trimmed = content.trim();
  const tooLong = trimmed.length > MAX_LENGTH;
  const canSubmit = trimmed.length > 0 && !tooLong && !createMutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    createMutation.mutate(
      { content: trimmed },
      {
        onSuccess: () => setContent(''),
      },
    );
  };

  return (
    <form
      onSubmit={handleSubmit}
      className='rounded-xl border border-[#2a2a3d] bg-[#1e1e2e] p-4'
    >
      <label
        htmlFor='memory-content'
        className='mb-2 block text-xs font-semibold uppercase tracking-widest text-[#6b6b8a]'
      >
        Add memory
      </label>
      <Textarea
        id='memory-content'
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder='Anything you want AXON to remember…'
        rows={3}
        maxLength={MAX_LENGTH}
        className='resize-none border-[#2a2a3d] bg-[#13131b] text-sm text-[#e4e1ed] placeholder:text-[#6b6b8a] focus-visible:ring-[#494bd6]'
      />
      <div className='mt-2 flex items-center justify-between gap-3'>
        <span
          className={`text-[10px] ${
            tooLong ? 'text-[#ffb4ab]' : 'text-[#6b6b8a]'
          }`}
        >
          {trimmed.length} / {MAX_LENGTH}
        </span>
        <Button
          type='submit'
          disabled={!canSubmit}
          className='gap-1.5 bg-[#494bd6] text-white hover:bg-[#5b5dd9] disabled:bg-[#2a2a3d] disabled:text-[#6b6b8a]'
        >
          <Plus className='h-4 w-4' />
          {createMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>

      {createMutation.isError && (
        <p className='mt-2 text-xs text-[#ffb4ab]'>
          {createMutation.error.message}
        </p>
      )}
    </form>
  );
};

export default MemoryCreateForm;
