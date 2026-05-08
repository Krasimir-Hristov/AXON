export interface ChatModel {
  id: string;
  name: string;
  provider: string;
  context_length: number;
  category: string;
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

/** Alias kept for backward compatibility — identical to Conversation. */
export type ConversationOut = Conversation;

/** Mirrors backend MessageOut schema. */
export interface MessageOut {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  created_at: string;
}

export type SSEEventType = 'start' | 'token' | 'tool_use' | 'error' | 'done';

export interface SSEEvent {
  type: SSEEventType;
  content: string;
}
