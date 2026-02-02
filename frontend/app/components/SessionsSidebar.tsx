'use client';

import { useState, useEffect, useCallback } from 'react';
import { fetchSessions, deleteSession, Session } from '../lib/api';

interface SessionsSidebarProps {
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession?: (sessionId: string) => void;
  onToggleSidebar?: () => void;
}

export default function SessionsSidebar({ activeSessionId, onSelectSession, onNewChat, onDeleteSession, onToggleSidebar }: SessionsSidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch {
      // Silently fail
    }
  }, []);

  useEffect(() => {
    loadSessions();
    const interval = setInterval(loadSessions, 5000);
    return () => clearInterval(interval);
  }, [loadSessions]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setDeletingId(sessionId);
    try {
      await deleteSession(sessionId);
      // Wait for the slide-out animation to finish before removing from list
      setTimeout(() => {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
        setDeletingId(null);
        if (activeSessionId === sessionId) {
          onDeleteSession?.(sessionId);
        }
      }, 400);
    } catch {
      setDeletingId(null);
    }
  };

  return (
    <div className="flex flex-col h-full bg-sand-50">
      {/* Toolbar: toggle + new chat */}
      <div className="p-3 flex items-center gap-2">
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="flex w-8 h-8 items-center justify-center rounded-lg shrink-0
                       text-sand-400 hover:text-sand-600 hover:bg-sand-100 transition-colors cursor-pointer"
            title="Hide sidebar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
              <path d="M3 6h10M3 12h18M3 18h10" />
            </svg>
          </button>
        )}
        <button
          onClick={onNewChat}
          className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg border border-sand-200
                     hover:bg-sand-100 transition-colors text-sm font-medium text-sand-600 cursor-pointer"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto chat-scroll px-2 pb-3 space-y-0.5">
        {sessions.length === 0 && (
          <p className="text-xs text-sand-400 text-center mt-4">No conversations yet</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => deletingId !== s.session_id && onSelectSession(s.session_id)}
            className={`group w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-300 cursor-pointer overflow-hidden
                        ${deletingId === s.session_id
                          ? 'bg-brand-orange-100 border border-brand-orange-500/30 text-brand-orange-600 opacity-0 max-h-0 py-0 my-0 translate-x-full'
                          : activeSessionId === s.session_id
                            ? 'bg-sand-200 text-sand-800 max-h-20'
                            : 'text-sand-500 hover:bg-sand-100 hover:text-sand-700 max-h-20'
                        }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">
                {s.first_message ? s.first_message.slice(0, 40) : 'New conversation'}
              </span>
              <button
                onClick={(e) => handleDelete(e, s.session_id)}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-sand-300 hover:text-brand-orange-600 p-0.5 shrink-0 cursor-pointer"
                title="Delete chat"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
