import { createClient } from '@/lib/supabase/client';
import { z } from 'zod';
import type { SSEEvent } from '@/features/chat/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** Read an error response body for rich error messages. */
async function _readErrorBody(response: Response): Promise<string> {
  try {
    const json = (await response.clone().json()) as Record<string, unknown>;
    const detail = json['detail'];
    return typeof detail === 'string' ? detail : JSON.stringify(json);
  } catch {
    return response.clone().text().catch(() => '');
  }
}

/**
 * Validates the Supabase session and returns the raw access token.
 * Throws if the user is unauthenticated or the session has expired.
 */
async function getAuthToken(): Promise<string> {
  const supabase = createClient();

  // getUser() validates the token with the Supabase server and refreshes if needed
  const { error } = await supabase.auth.getUser();
  if (error) throw new Error('Not authenticated');

  // After getUser(), getSession() is guaranteed to have a fresh access_token
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error('Not authenticated');
  }

  return session.access_token;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });

  if (!response.ok) {
    const body = await _readErrorBody(response);
    throw new Error(`HTTP ${response.status}: ${response.statusText}${body ? ` — ${body}` : ''}`);
  }

  return response.json() as Promise<T>;
}

export async function apiFetchPublic<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);

  if (!response.ok) {
    const body = await _readErrorBody(response);
    throw new Error(`HTTP ${response.status}: ${response.statusText}${body ? ` — ${body}` : ''}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Authenticated fetch for endpoints returning no JSON body (e.g. 204 No Content).
 * Throws on non-ok status; otherwise resolves to `void`.
 */
export async function apiFetchVoid(
  path: string,
  init?: RequestInit,
): Promise<void> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });

  if (!response.ok) {
    const body = await _readErrorBody(response);
    throw new Error(`HTTP ${response.status}: ${response.statusText}${body ? ` — ${body}` : ''}`);
  }
}

/**
 * Authenticated multipart upload — does NOT set `Content-Type` so the browser
 * adds the correct `multipart/form-data; boundary=…` automatically.
 */
export async function apiFetchMultipart<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const token = await getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const body = await _readErrorBody(response);
    throw new Error(`HTTP ${response.status}: ${response.statusText}${body ? ` — ${body}` : ''}`);
  }

  return response.json() as Promise<T>;
}

export interface StreamChatPayload {
  message: string;
  model_id: string;
  conversation_id?: string;
}

const _streamChatSchema = z.object({
  message: z.string().min(1),
  model_id: z.string().min(1),
  conversation_id: z.string().optional(),
});

export async function streamChat(
  payload: StreamChatPayload,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  _streamChatSchema.parse(payload);
  const headers = await getAuthHeaders();

  const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const { EventSourceParserStream } = await import('eventsource-parser/stream');

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
    .getReader();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      if (value.data) {
        try {
          const parsed = JSON.parse(value.data) as SSEEvent;
          onEvent(parsed);
          if (parsed.type === 'done' || parsed.type === 'error') break;
        } catch {
          // skip malformed frames
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
