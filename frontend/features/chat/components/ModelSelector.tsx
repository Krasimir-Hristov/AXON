'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import { useModels } from '@/features/chat/hooks/useModels';
import type { ChatModel } from '@/features/chat/types';

interface ModelSelectorProps {
  selectedModelId: string;
  onModelChange: (modelId: string) => void;
  disabled?: boolean;
}

const ModelSelector = ({
  selectedModelId,
  onModelChange,
  disabled,
}: ModelSelectorProps) => {
  const { data: models, isLoading, isError } = useModels();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedModel = models?.find((m) => m.id === selectedModelId);

  // Close dropdown on outside click
  useEffect(() => {
    const handlePointerDown = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, []);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, []);

  // Filter by search only
  const q = search.toLowerCase();
  const filtered: ChatModel[] = !models
    ? []
    : !q
      ? models
      : models.filter(
          (m) =>
            m.name.toLowerCase().includes(q) ||
            m.provider.toLowerCase().includes(q) ||
            m.id.toLowerCase().includes(q),
        );

  // Group filtered models by provider
  const grouped: Record<string, ChatModel[]> = {};
  for (const m of filtered) {
    if (!grouped[m.provider]) grouped[m.provider] = [];
    grouped[m.provider].push(m);
  }

  const handleSelect = (modelId: string) => {
    onModelChange(modelId);
    setOpen(false);
    setSearch('');
  };

  if (isError) {
    return (
      <span className='text-xs text-[#ffb4ab]'>Failed to load models</span>
    );
  }

  return (
    <div ref={containerRef} className='relative'>
      {/* Trigger */}
      <button
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled || isLoading}
        className='flex items-center gap-1.5 rounded-lg border border-[#2a2a3d] bg-[#1e1e2e] px-3 py-1.5 text-sm text-[#e4e1ed] transition-colors hover:bg-[#2a2a3d] disabled:cursor-not-allowed disabled:opacity-50'
        aria-haspopup='listbox'
        aria-expanded={open}
      >
        <span className='max-w-40 truncate'>
          {isLoading ? 'Loading…' : (selectedModel?.name ?? 'Select model')}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 text-[#6b6b8a] transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className='absolute right-0 top-full z-50 mt-1.5 w-80 overflow-hidden rounded-xl border border-[#2a2a3d] bg-[#1e1e2e] shadow-2xl shadow-black/50'>
          {/* Search */}
          <div className='flex items-center gap-2 border-b border-[#2a2a3d] px-3 py-2.5'>
            <Search className='h-3.5 w-3.5 shrink-0 text-[#6b6b8a]' />
            <input
              autoFocus
              aria-label='Search models'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Search models…'
              className='flex-1 bg-transparent text-sm text-[#e4e1ed] placeholder:text-[#6b6b8a] focus:outline-none'
            />
          </div>

          {/* Model list */}
          <div className='max-h-72 overflow-y-auto' role='listbox'>
            {Object.keys(grouped).length === 0 ? (
              <p className='py-8 text-center text-xs text-[#6b6b8a]'>
                No models found
              </p>
            ) : (
              Object.entries(grouped).map(([provider, providerModels]) => (
                <div key={provider}>
                  <p className='sticky top-0 bg-[#1e1e2e] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-[#494bd6]'>
                    {provider}
                  </p>
                  {providerModels.map((model) => (
                    <button
                      key={model.id}
                      role='option'
                      aria-selected={model.id === selectedModelId}
                      onClick={() => handleSelect(model.id)}
                      className='flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-[#2a2a3d]'
                    >
                      <div className='min-w-0 flex-1'>
                        <p className='truncate text-sm text-[#e4e1ed]'>
                          {model.name}
                        </p>
                        <p className='text-[10px] text-[#6b6b8a]'>
                          {model.category}
                          {model.context_length > 0 &&
                            ` · ${(model.context_length / 1000).toFixed(0)}k ctx`}
                        </p>
                      </div>
                      {model.id === selectedModelId && (
                        <Check className='ml-2 h-3.5 w-3.5 shrink-0 text-[#494bd6]' />
                      )}
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelSelector;
