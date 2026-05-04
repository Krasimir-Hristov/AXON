'use client';

import { useState, KeyboardEvent } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { SendHorizonal, Square } from 'lucide-react';

interface ChatInputProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

const ChatInput = ({ onSend, onStop, isStreaming }: ChatInputProps) => {
  const [value, setValue] = useState('');

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className='flex items-end gap-2 border-t border-[#2a2a3d] bg-[#13131b] p-4'>
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder='Message AXON… (Enter to send, Shift+Enter for newline)'
        disabled={isStreaming}
        rows={1}
        className='min-h-11 flex-1 resize-none border-[#2a2a3d] bg-[#1e1e2e] text-[#e4e1ed] placeholder:text-[#6b6b8a] focus-visible:ring-[#494bd6] disabled:opacity-50'
      />
      {isStreaming ? (
        <Button
          onClick={onStop}
          size='icon'
          variant='outline'
          className='shrink-0 border-[#2a2a3d] bg-[#1e1e2e] text-[#e4e1ed] hover:bg-[#2a2a3d]'
          aria-label='Stop generation'
        >
          <Square className='h-4 w-4' />
        </Button>
      ) : (
        <Button
          onClick={handleSend}
          size='icon'
          disabled={!value.trim()}
          className='shrink-0 bg-[#494bd6] text-white hover:bg-[#3a3cb8] disabled:opacity-40'
          aria-label='Send message'
        >
          <SendHorizonal className='h-4 w-4' />
        </Button>
      )}
    </div>
  );
};

export default ChatInput;
