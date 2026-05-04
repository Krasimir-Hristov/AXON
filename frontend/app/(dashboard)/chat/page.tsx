import { redirect } from 'next/navigation';
import { createClient } from '@/lib/supabase/server';
import ChatWindow from '@/features/chat/components/ChatWindow';

const ChatPage = async () => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect('/login');

  return (
    <main className='h-screen'>
      <ChatWindow />
    </main>
  );
};

export default ChatPage;
