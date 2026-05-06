'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Sparkles, PenLine, Brain } from 'lucide-react';
import { Button } from '@/components/ui/button';

import MessageBubble from '@/features/chat/components/MessageBubble';
import ChatInput from '@/features/chat/components/ChatInput';
import ModelSelector from '@/features/chat/components/ModelSelector';
import { useChat } from '@/features/chat/hooks/useChat';
import { useModels } from '@/features/chat/hooks/useModels';

/** Permanent background: AI robot face image */
const AiFaceBackground = () => (
  <div className='pointer-events-none absolute inset-0 overflow-hidden'>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img
      src='/axon_background.png'
      alt=''
      aria-hidden='true'
      className='h-full w-full object-cover opacity-30'
    />
  </div>
);

const ChatWindow = () => {
  const {
    messages,
    isStreaming,
    error,
    sendMessage,
    stopStreaming,
    resetConversation,
  } = useChat();
  const { data: models } = useModels();
  const [selectedModelId, setSelectedModelId] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Set default model once models load
  useEffect(() => {
    if (models && models.length > 0 && !selectedModelId) {
      setSelectedModelId(models[0].id);
    }
  }, [models, selectedModelId]);

  // Auto-scroll on new messages / streaming tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: isStreaming ? 'auto' : 'smooth',
    });
  }, [messages, isStreaming]);

  function handleSend(content: string) {
    if (!selectedModelId) return;
    sendMessage(content, selectedModelId);
  }

  const hasMessages = messages.length > 0;

  return (
    <div className='flex h-full flex-col bg-[#13131b]'>
      {/* Header */}
      <div className='flex shrink-0 items-center justify-between border-b border-[#2a2a3d] px-5 py-3'>
        <div className='flex items-center gap-2.5'>
          <div className='flex h-6 w-6 items-center justify-center rounded-md bg-[#494bd6]/20'>
            <Sparkles className='h-3.5 w-3.5 text-[#c0c1ff]' />
          </div>
          <span className='text-sm font-semibold text-[#e4e1ed]'>AXON</span>
        </div>

        <div className='flex items-center gap-2'>
          <ModelSelector
            selectedModelId={selectedModelId}
            onModelChange={setSelectedModelId}
            disabled={isStreaming}
          />
          <Link
            href='/memory'
            className='inline-flex h-9 w-9 items-center justify-center rounded-md text-[#6b6b8a] transition-colors hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
            aria-label='Memory'
            title='Memory'
          >
            <Brain className='h-4 w-4' />
          </Link>
          <Button
            onClick={resetConversation}
            size='icon'
            variant='ghost'
            disabled={!hasMessages}
            className='text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#e4e1ed] disabled:pointer-events-none disabled:opacity-30'
            aria-label='New conversation'
            title='New conversation'
          >
            <PenLine className='h-4 w-4' />
          </Button>
        </div>
      </div>

      {/* Messages area — AI face lives behind all content */}
      <div className='relative flex-1 overflow-hidden'>
        <AiFaceBackground />
        <ScrollArea className='h-full px-4'>
          <div className='mx-auto max-w-3xl py-6'>
            <div className='space-y-6'>
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              {error && !isStreaming && (
                <p className='text-center text-xs text-[#ffb4ab]'>{error}</p>
              )}
            </div>
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </div>

      {/* Input */}
      <div className='shrink-0'>
        <div className='mx-auto w-full max-w-3xl'>
          <ChatInput
            onSend={handleSend}
            onStop={stopStreaming}
            isStreaming={isStreaming}
          />
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
