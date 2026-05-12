'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sparkles,
  PenLine,
  Brain,
  Database,
  Play,
  Bookmark,
  Volume2,
  Menu,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useQueryClient } from '@tanstack/react-query';

import MessageBubble from '@/features/chat/components/MessageBubble';
import ChatInput from '@/features/chat/components/ChatInput';
import ModelSelector from '@/features/chat/components/ModelSelector';
import ConversationSidebar from '@/features/chat/components/ConversationSidebar';
import { useChat } from '@/features/chat/hooks/useChat';
import { useModels } from '@/features/chat/hooks/useModels';
import { usePreferredModel } from '@/features/chat/hooks/usePreferredModel';
import {
  CONVERSATIONS_KEY,
  useConversationMessages,
} from '@/features/chat/hooks/useConversations';

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
    conversationId,
    error,
    toolStatus,
    sendMessage,
    stopStreaming,
    resetConversation,
    loadConversation,
  } = useChat();
  const { data: models } = useModels();
  const {
    preferredModelId,
    loaded: prefLoaded,
    changeModel,
  } = usePreferredModel();
  const [selectedModelId, setSelectedModelId] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // id whose messages we're about to load (pending load pattern)
  const [pendingLoadId, setPendingLoadId] = useState<string | undefined>();
  const bottomRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  // Fetch messages for the pending conversation selection
  const { data: pendingMessages } = useConversationMessages(pendingLoadId);

  // Set initial model from saved preference (falls back to first available model)
  useEffect(() => {
    if (!prefLoaded || !models || models.length === 0 || selectedModelId)
      return;
    const saved = models.find((m) => m.id === preferredModelId);
    setSelectedModelId(saved ? saved.id : models[0].id);
  }, [prefLoaded, models, preferredModelId, selectedModelId]);

  // Load conversation once its messages arrive
  useEffect(() => {
    if (!pendingLoadId || !pendingMessages) return;
    loadConversation(pendingLoadId, pendingMessages);
    setPendingLoadId(undefined);
  }, [pendingLoadId, pendingMessages, loadConversation]);

  // Auto-scroll on new messages / streaming tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: isStreaming ? 'auto' : 'smooth',
    });
  }, [messages, isStreaming]);

  // After streaming ends, invalidate the conversation list so updated_at re-sorts
  useEffect(() => {
    if (!isStreaming && conversationId) {
      void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
    }
    // Only run when isStreaming transitions to false
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming]);

  // Close mobile sidebar on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setSidebarOpen(false);
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  function handleSend(content: string) {
    if (!selectedModelId) return;
    sendMessage(content, selectedModelId);
  }

  function handleConversationSelect(id: string) {
    setSidebarOpen(false);
    setPendingLoadId(id);
  }

  function handleNew() {
    setSidebarOpen(false);
    resetConversation();
  }

  function handleDeleted(id: string) {
    if (id === conversationId) resetConversation();
  }

  const hasMessages = messages.length > 0;

  return (
    <div className='flex h-full bg-[#13131b]'>
      {/* ── Desktop sidebar (260 px, hidden on mobile) ── */}
      <div className='hidden md:flex'>
        <ConversationSidebar
          activeId={conversationId}
          onSelect={handleConversationSelect}
          onNew={handleNew}
          onDeleted={handleDeleted}
        />
      </div>

      {/* ── Mobile sidebar drawer ── */}
      {sidebarOpen && (
        <>
          {/* Backdrop */}
          <div
            className='fixed inset-0 z-30 bg-black/60 md:hidden'
            onClick={() => setSidebarOpen(false)}
            aria-hidden='true'
          />
          {/* Drawer */}
          <div className='fixed inset-y-0 left-0 z-40 md:hidden'>
            <ConversationSidebar
              activeId={conversationId}
              onSelect={handleConversationSelect}
              onNew={handleNew}
              onDeleted={handleDeleted}
            />
          </div>
        </>
      )}

      {/* ── Main chat column ── */}
      <div className='flex min-w-0 flex-1 flex-col'>
        {/* Header */}
        <div className='flex shrink-0 items-center justify-between border-b border-[#2a2a3d] px-5 py-3'>
          <div className='flex items-center gap-2.5'>
            {/* Hamburger (mobile only) */}
            <Button
              size='icon'
              variant='ghost'
              onClick={() => setSidebarOpen((v) => !v)}
              className='md:hidden text-[#6b6b8a] hover:bg-[#2a2a3d] hover:text-[#e4e1ed]'
              aria-label='Toggle conversation list'
            >
              {sidebarOpen ? (
                <X className='h-4 w-4' />
              ) : (
                <Menu className='h-4 w-4' />
              )}
            </Button>

            <div className='flex h-6 w-6 items-center justify-center rounded-md bg-[#494bd6]/20'>
              <Sparkles className='h-3.5 w-3.5 text-[#c0c1ff]' />
            </div>
            <span className='text-sm font-semibold text-[#e4e1ed]'>AXON</span>
          </div>

          <div className='flex items-center gap-2'>
            <ModelSelector
              selectedModelId={selectedModelId}
              onModelChange={(id) => {
                setSelectedModelId(id);
                changeModel(id);
              }}
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
                {toolStatus && (
                  <div className='flex items-center gap-2 text-xs text-[#c0c1ff]'>
                    {toolStatus.startsWith('Fetching YouTube') ? (
                      <Play className='h-3.5 w-3.5 shrink-0 animate-pulse text-red-400' />
                    ) : toolStatus.startsWith('Saving') ? (
                      <Bookmark className='h-3.5 w-3.5 shrink-0 animate-pulse text-[#c0c1ff]' />
                    ) : toolStatus.startsWith('Generating audio') ? (
                      <Volume2 className='h-3.5 w-3.5 shrink-0 animate-pulse text-purple-400' />
                    ) : (
                      <Database className='h-3.5 w-3.5 shrink-0 animate-pulse' />
                    )}
                    <span>{toolStatus}</span>
                  </div>
                )}
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
    </div>
  );
};

export default ChatWindow;
