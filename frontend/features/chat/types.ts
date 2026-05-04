export interface ChatModel {
  id: string;
  name: string;
  provider: string;
  context_length: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  /** True while this assistant message is still being streamed */
  isStreaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  model_id: string;
  created_at: string;
  updated_at: string;
}

export type SSEEventType = 'start' | 'token' | 'error' | 'done';

export interface SSEEvent {
  type: SSEEventType;
  content: string;
}
