import { redirect } from 'next/navigation';
import { createClient } from '@/lib/supabase/server';
import MemoryView from '@/features/memory/components/MemoryView';

const MemoryPage = async () => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect('/login');

  return (
    <main className='h-screen'>
      <MemoryView />
    </main>
  );
};

export default MemoryPage;
