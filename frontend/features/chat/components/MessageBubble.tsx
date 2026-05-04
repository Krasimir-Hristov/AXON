'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '@/features/chat/types';

interface MessageBubbleProps {
  message: Message;
}

const ThinkingDots = () => (
  <span className='inline-flex items-center gap-1' aria-label='Thinking'>
    {[0, 1, 2].map((i) => (
      <span
        key={i}
        className='inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b6b8a]'
        style={{ animationDelay: `${i * 0.15}s` }}
      />
    ))}
  </span>
);

const TypingCaret = () => (
  <span
    aria-hidden='true'
    className='ml-0.5 inline-block h-4 w-0.5 -translate-y-px animate-pulse bg-[#c0c1ff] align-middle'
  />
);

const MessageBubble = ({ message }: MessageBubbleProps) => {
  const isUser = message.role === 'user';
  const isEmptyStreaming = message.isStreaming && message.content === '';

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? 'rounded-br-sm bg-[#494bd6] text-white'
            : 'rounded-bl-sm bg-[#1e1e2e] text-[#e4e1ed]'
        }`}
      >
        {isEmptyStreaming ? (
          <ThinkingDots />
        ) : (
          <div className='relative'>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => (
                  <pre className='mt-2 overflow-x-auto rounded-lg bg-[#0d0d17] p-3 text-xs'>
                    {children}
                  </pre>
                ),
                code: ({ children, className }) =>
                  className ? (
                    <code className={className}>{children}</code>
                  ) : (
                    <code className='rounded bg-[#0d0d17] px-1 py-0.5 text-xs text-[#c0c1ff]'>
                      {children}
                    </code>
                  ),
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-[#c0c1ff] underline underline-offset-2 hover:text-white'
                  >
                    {children}
                  </a>
                ),
                p: ({ children }) => (
                  <p className='not-first:mt-2'>{children}</p>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
            {message.isStreaming && !isUser && <TypingCaret />}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
