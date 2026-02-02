'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { sendChatMessage, fetchMessages, ChatMessage } from '../lib/api';

// ---------------------------------------------------------------------------
// Block types for structured assistant messages
// ---------------------------------------------------------------------------

interface MessageBlock {
  type: 'text' | 'thinking' | 'tool_use';
  content: string;
  name?: string; // tool name, only for tool_use
}

interface StructuredMessage {
  role: 'user' | 'assistant';
  content: string;       // plain text (persistence & history fallback)
  blocks?: MessageBlock[]; // structured blocks built during streaming
}

// ---------------------------------------------------------------------------
// Collapsible block renderers
// ---------------------------------------------------------------------------

function ThinkingBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!content) return null;
  const wordCount = content.trim().split(/\s+/).length;
  return (
    <div className="my-1.5 border border-sand-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-1.5 bg-sand-50 hover:bg-sand-100 transition-colors text-left"
      >
        <svg className={`w-3.5 h-3.5 text-sand-400 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6" /></svg>
        <svg className="w-3.5 h-3.5 text-brand-fig" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1h-6a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7zM9 21h6M10 21v-1h4v1" /></svg>
        <span className="text-xs font-medium text-sand-600">Thinking</span>
        {!expanded && <span className="text-xs text-sand-400 ml-auto">{wordCount} words</span>}
      </button>
      {expanded && (
        <div className="px-3 py-2 text-xs text-sand-600 whitespace-pre-wrap border-t border-sand-100 max-h-64 overflow-y-auto">
          {content}
        </div>
      )}
    </div>
  );
}

function ToolUseBlock({ name, content, isStreaming }: { name: string; content: string; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  let prettyInput = content;
  try { prettyInput = JSON.stringify(JSON.parse(content), null, 2); } catch { /* show raw */ }
  return (
    <div className="my-1.5 border border-sand-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-1.5 bg-sand-50 hover:bg-sand-100 transition-colors text-left"
      >
        <svg className="w-3.5 h-3.5 text-brand-fig" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" /></svg>
        <span className="text-xs font-medium text-sand-600">{name}</span>
        {isStreaming && <span className="text-xs text-sand-400 ml-1 animate-pulse">●</span>}
        <svg className={`w-3.5 h-3.5 text-sand-400 ml-auto transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6" /></svg>
      </button>
      {expanded && (
        <div className="px-3 py-2 text-xs font-mono text-sand-600 border-t border-sand-100 max-h-64 overflow-y-auto whitespace-pre-wrap bg-sand-50">
          {prettyInput || '…'}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Persistence helpers — store the full messages array (content + blocks) in
// localStorage so partial responses and structured blocks survive page
// refreshes, navigation, and mid-stream aborts.
// ---------------------------------------------------------------------------

function saveMessagesToStorage(sessionId: string, messages: StructuredMessage[]) {
  try {
    localStorage.setItem(`chat-data-${sessionId}`, JSON.stringify(messages));
  } catch { /* quota exceeded — best-effort */ }
}

function restoreMessages(sessionId: string, backendMessages: StructuredMessage[]): StructuredMessage[] {
  try {
    const stored = localStorage.getItem(`chat-data-${sessionId}`);
    if (!stored) return backendMessages;
    const local: StructuredMessage[] = JSON.parse(stored);

    // Backend is authoritative for message content; localStorage provides
    // blocks and any trailing partial messages the backend never received
    // (e.g. an assistant response interrupted by abort).
    const merged = backendMessages.map((msg, i) => ({
      ...msg,
      blocks: local[i]?.blocks ?? undefined,
    }));

    // Append messages that exist locally but not in the backend
    for (let i = backendMessages.length; i < local.length; i++) {
      merged.push(local[i]);
    }

    return merged;
  } catch {
    return backendMessages;
  }
}

// ---------------------------------------------------------------------------

interface ChatPanelProps {
  sessionId: string | null;
  onSessionChange: (sessionId: string) => void;
}

export default function ChatPanel({ sessionId, onSessionChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<StructuredMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load messages when sessionId changes, restoring blocks & partial messages
  useEffect(() => {
    if (sessionId) {
      fetchMessages(sessionId)
        .then((msgs) => setMessages(restoreMessages(sessionId, msgs)))
        .catch(() => setMessages([]));
    } else {
      setMessages([]);
    }
  }, [sessionId]);

  // Reset textarea height when input is cleared
  useEffect(() => {
    if (!input && inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    setError(null);
    const userMsg: ChatMessage = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsStreaming(true);

    // Add empty assistant message to stream into
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    await sendChatMessage(
      trimmed,
      sessionId,
      (event) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role !== 'assistant') return prev;

          const blocks: MessageBlock[] = [...(last.blocks || [])];
          let content = last.content;

          if (event.content) {
            // Text delta — append to last text block or start a new one
            const lastBlock = blocks[blocks.length - 1];
            if (lastBlock && lastBlock.type === 'text') {
              blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + event.content };
            } else {
              blocks.push({ type: 'text', content: event.content as string });
            }
            content += event.content as string;
          } else if (event.thinking_start) {
            blocks.push({ type: 'thinking', content: '' });
          } else if (event.thinking) {
            const lastBlock = blocks[blocks.length - 1];
            if (lastBlock && lastBlock.type === 'thinking') {
              blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + (event.thinking as string) };
            }
          } else if (event.tool_use_start) {
            const info = event.tool_use_start as { name: string };
            blocks.push({ type: 'tool_use', content: '', name: info.name });
          } else if (event.tool_use_input) {
            const lastBlock = blocks[blocks.length - 1];
            if (lastBlock && lastBlock.type === 'tool_use') {
              blocks[blocks.length - 1] = { ...lastBlock, content: lastBlock.content + (event.tool_use_input as string) };
            }
          }
          // block_stop: no state change needed — next delta auto-starts a new block

          updated[updated.length - 1] = { ...last, content, blocks };
          return updated;
        });
      },
      () => {
        abortControllerRef.current = null;
        setIsStreaming(false);
        const sid = sessionStorage.getItem('chat_session_id');
        if (sid) {
          // Persist full messages (content + blocks) so partial responses
          // and structured blocks survive refresh / navigation / abort.
          setMessages((prev) => {
            saveMessagesToStorage(sid, prev);
            return prev;
          });
          onSessionChange(sid);
        }
      },
      (err) => {
        abortControllerRef.current = null;
        setIsStreaming(false);
        setError(err.message);
        // Remove empty assistant message on error
        setMessages((prev) => {
          if (prev[prev.length - 1]?.content === '') {
            return prev.slice(0, -1);
          }
          return prev;
        });
      },
      controller.signal,
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto chat-scroll px-6 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full text-sand-400 text-sm pt-32">
              <div className="text-center space-y-3">
                <div className="w-12 h-12 mx-auto rounded-full bg-brand-coral/30 flex items-center justify-center">
                  <svg className="w-6 h-6 text-brand-fig" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47 2.47a2.25 2.25 0 01-1.591.659H9.061a2.25 2.25 0 01-1.591-.659L5 14.5m14 0V17a2 2 0 01-2 2H7a2 2 0 01-2-2v-2.5" />
                  </svg>
                </div>
                <p className="text-sand-600">Start a conversation to capture experiment metadata.</p>
                <p className="text-xs text-sand-400">
                  Try: &quot;I ran a two-photon calcium imaging session on mouse
                  123 today&quot;
                </p>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={
                  msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-agent'
                }
              >
                <div className="text-sm leading-relaxed prose prose-sm max-w-none
                              prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
                              prose-strong:text-inherit prose-headings:text-inherit
                              prose-headings:text-base prose-headings:mt-2 prose-headings:mb-1">
                  {msg.role === 'assistant' ? (
                    msg.blocks && msg.blocks.length > 0 ? (
                      <>
                        {msg.blocks.map((block, idx) =>
                          block.type === 'text' ? (
                            <ReactMarkdown key={idx} remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
                          ) : block.type === 'thinking' ? (
                            <ThinkingBlock key={idx} content={block.content} />
                          ) : block.type === 'tool_use' ? (
                            <ToolUseBlock
                              key={idx}
                              name={block.name || 'tool'}
                              content={block.content}
                              isStreaming={isStreaming && i === messages.length - 1 && idx === msg.blocks!.length - 1}
                            />
                          ) : null
                        )}
                      </>
                    ) : (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    )
                  ) : (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  )}
                  {isStreaming &&
                    i === messages.length - 1 &&
                    msg.role === 'assistant' && (
                      <span className="streaming-cursor" />
                    )}
                </div>
              </div>
            </div>
          ))}

          {error && (
            <div className="bg-brand-orange-100 border border-brand-orange-500/20 text-brand-orange-600 rounded-lg px-4 py-3 text-sm">
              Connection error: {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="px-6 pb-6 pt-2">
        <div className="max-w-3xl mx-auto relative">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
            onKeyDown={handleKeyDown}
            placeholder="Describe your experiment..."
            rows={1}
            className="w-full resize-none rounded-2xl border border-sand-200 shadow-sm
                       px-4 pt-3 pb-12 text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand-fig/30 focus:border-brand-fig/50
                       disabled:bg-sand-50 disabled:text-sand-400
                       placeholder:text-sand-400"
            disabled={isStreaming}
          />
          <div className="absolute right-3 bottom-3">
            {isStreaming ? (
              <button
                onClick={() => abortControllerRef.current?.abort()}
                className="w-9 h-9 rounded-xl border border-sand-300 bg-white
                           flex items-center justify-center text-sand-600
                           hover:bg-sand-50 transition-colors"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                  <rect x="3" y="3" width="10" height="10" rx="1.5" />
                </svg>
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="w-9 h-9 rounded-xl bg-brand-fig
                           flex items-center justify-center text-white
                           hover:bg-brand-magenta-600 transition-colors
                           disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
