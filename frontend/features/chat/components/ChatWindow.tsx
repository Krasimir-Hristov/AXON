'use client';

import { useEffect, useRef, useState } from 'react';
import { ScrollArea } from '@/components/ui/scroll-area';

import MessageBubble from '@/features/chat/components/MessageBubble';
import ChatInput from '@/features/chat/components/ChatInput';
import ModelSelector from '@/features/chat/components/ModelSelector';
import { useChat } from '@/features/chat/hooks/useChat';
import { useModels } from '@/features/chat/hooks/useModels';
import { PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';

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

  // Auto-scroll to bottom on new messages / streaming tokens.
  // Use instant scroll during streaming to avoid competing animations.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: isStreaming ? 'auto' : 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = (content: string) => {
    if (!selectedModelId) return;
    sendMessage(content, selectedModelId);
  };

  return (
    <div className='flex h-full flex-col bg-[#13131b]'>
      {/* Header */}
      <div className='flex items-center justify-between border-b border-[#2a2a3d] px-4 py-3'>
        <h1 className='text-sm font-semibold text-[#e4e1ed]'>AXON</h1>
        <div className='flex items-center gap-3'>
          <ModelSelector
            selectedModelId={selectedModelId}
            onModelChange={setSelectedModelId}
            disabled={isStreaming}
          />
          <Button
            onClick={resetConversation}
            size='icon'
            variant='ghost'
            className='text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
            aria-label='New conversation'
            title='New conversation'
          >
            <PenLine className='h-4 w-4' />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className='flex-1 px-4'>
        <div className='mx-auto max-w-3xl space-y-4 py-6'>
          {messages.length === 0 && (
            <div className='flex h-full flex-col items-center justify-center py-20 text-center'>
              <p className='text-[#6b6b8a]'>Start a conversation with AXON</p>
            </div>
          )}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {error && !isStreaming && (
            <p className='text-center text-xs text-[#ffb4ab]'>{error}</p>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className='mx-auto w-full max-w-3xl'>
        <ChatInput
          onSend={handleSend}
          onStop={stopStreaming}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
};

export default ChatWindow;
