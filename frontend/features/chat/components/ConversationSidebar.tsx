'use client';

import { MessageSquarePlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useConversations } from '@/features/chat/hooks/useConversations';
import ConversationRow from './ConversationRow';
import SkeletonRow from './SkeletonRow';

interface ConversationSidebarProps {
  activeId: string | undefined;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
}

const ConversationSidebar = ({
  activeId,
  onSelect,
  onNew,
  onDeleted,
}: ConversationSidebarProps) => {
  const { data: conversations, isLoading } = useConversations();

  return (
    <aside className='flex h-full w-65 shrink-0 flex-col border-r border-[#2a2a3d] bg-[#0f0f17]'>
      {/* New chat */}
      <div className='shrink-0 border-b border-[#2a2a3d] p-3'>
        <Button
          type='button'
          variant='ghost'
          onClick={onNew}
          className='w-full justify-start gap-2 text-[#9b9bb8] hover:bg-[#1e1e2e] hover:text-[#e4e1ed] cursor-pointer'
        >
          <MessageSquarePlus className='h-4 w-4' />
          <span className='text-sm'>New chat</span>
        </Button>
      </div>

      {/* List */}
      <ScrollArea className='flex-1 px-2 py-2'>
        {isLoading ? (
          <div className='space-y-1'>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : !conversations || conversations.length === 0 ? (
          <p className='px-3 py-6 text-center text-xs text-[#6b6b8a]'>
            No conversations yet
          </p>
        ) : (
          <div className='space-y-0.5'>
            {conversations.map((conv) => (
              <ConversationRow
                key={conv.id}
                conversation={conv}
                isActive={conv.id === activeId}
                onSelect={() => onSelect(conv.id)}
                onDeleted={() => onDeleted(conv.id)}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
};

export default ConversationSidebar;
