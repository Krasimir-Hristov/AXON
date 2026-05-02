import { createClient } from '@/lib/supabase/server';
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

const callbackSchema = z.object({
  code: z.string().min(1),
});

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const fallback = NextResponse.redirect(
    `${origin}/login?error=auth_callback_failed`,
  );

  const parsed = callbackSchema.safeParse({ code: searchParams.get('code') });
  if (!parsed.success) {
    return fallback;
  }

  try {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(
      parsed.data.code,
    );
    if (!error) {
      return NextResponse.redirect(`${origin}/chat`);
    }
  } catch {
    // Unexpected error during session exchange
  }

  return fallback;
}
