'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { fetchMetadata, confirmMetadata, MetadataEntry } from '../lib/api';

function StatusBadge({ status }: { status: string }) {
  const colors =
    status === 'confirmed'
      ? 'bg-brand-aqua-500/10 text-brand-aqua-700 border-brand-aqua-500/20'
      : 'bg-brand-orange-100 text-brand-orange-600 border-brand-orange-500/20';
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colors}`}
    >
      {status}
    </span>
  );
}

/** Flatten a nested metadata object into readable key-value pairs. */
function flattenFields(obj: unknown, prefix = ''): { label: string; value: string }[] {
  if (obj == null) return [];
  if (typeof obj !== 'object') return [{ label: prefix || 'value', value: String(obj) }];
  const entries: { label: string; value: string }[] = [];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const label = prefix ? `${prefix} > ${k.replace(/_/g, ' ')}` : k.replace(/_/g, ' ');
    if (v != null && typeof v === 'object' && !Array.isArray(v)) {
      const nested = v as Record<string, unknown>;
      // Collapse {name: "..."} objects down to just the parent key
      if (Object.keys(nested).length === 1 && 'name' in nested) {
        entries.push({ label, value: String(nested.name) });
      } else {
        entries.push(...flattenFields(v, label));
      }
    } else if (Array.isArray(v)) {
      entries.push({ label, value: v.map((item) => (typeof item === 'object' ? (item as Record<string, unknown>).name ?? JSON.stringify(item) : String(item))).join(', ') });
    } else {
      entries.push({ label, value: String(v) });
    }
  }
  return entries;
}

function MetadataCard({
  entry,
  onConfirm,
}: {
  entry: MetadataEntry;
  onConfirm: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const router = useRouter();

  return (
    <div
      className="metadata-card bg-white border border-sand-200 rounded-xl p-4 space-y-3 cursor-pointer hover:border-sand-300"
      onClick={() => router.push(`/dashboard#${entry.session_id}`)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-sand-800 truncate">
            {entry.subject_id || 'Untitled'}
          </p>
          <p className="text-xs text-sand-400">
            {new Date(entry.created_at).toLocaleDateString()}
          </p>
        </div>
        <StatusBadge status={entry.status} />
      </div>

      {/* Field preview */}
      <div className="space-y-1">
        {entry.fields && Object.keys(entry.fields).length > 0 ? (() => {
          const allRows = Object.entries(entry.fields).flatMap(([, val]) =>
            flattenFields(val)
          );
          const visibleRows = expanded ? allRows : allRows.slice(0, 5);
          return (
            <>
              {visibleRows.map((row, i) => (
                <div key={i} className="flex text-xs gap-2">
                  <span className="text-sand-400 shrink-0 w-32 truncate capitalize">
                    {row.label}:
                  </span>
                  <span className="text-sand-700 truncate">
                    {row.value}
                  </span>
                </div>
              ))}
              {allRows.length > 5 && (
                <button
                  onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
                  className="text-xs text-brand-fig hover:text-brand-magenta-800"
                >
                  {expanded ? 'Show less' : `+${allRows.length - 5} more fields`}
                </button>
              )}
            </>
          );
        })() : (
          <p className="text-xs text-sand-400 italic">No fields captured yet</p>
        )}
      </div>

      {entry.status === 'draft' && (
        <button
          onClick={(e) => { e.stopPropagation(); onConfirm(entry.session_id); }}
          className="w-full rounded-lg bg-sand-100 text-sand-600 text-xs font-medium py-2
                     hover:bg-sand-200 transition-colors border border-sand-200"
        >
          Confirm Metadata
        </button>
      )}
    </div>
  );
}

export default function MetadataSidebar() {
  const [entries, setEntries] = useState<MetadataEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'draft' | 'confirmed'>('all');

  const load = useCallback(async () => {
    try {
      const data = await fetchMetadata();
      setEntries(data);
    } catch {
      // API not available yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const handleConfirm = async (id: string) => {
    try {
      await confirmMetadata(id);
      load();
    } catch (err) {
      console.error('Failed to confirm:', err);
    }
  };

  const filtered =
    filter === 'all' ? entries : entries.filter((e) => e.status === filter);

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-4 border-b border-sand-200 bg-white">
        <h2 className="text-sm font-semibold text-sand-800">
          Captured Metadata
        </h2>
        <div className="flex gap-1 mt-2">
          {(['all', 'draft', 'confirmed'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === f
                  ? 'bg-sand-800 text-white'
                  : 'bg-sand-100 text-sand-500 hover:bg-sand-200'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
              {f !== 'all' &&
                ` (${entries.filter((e) => e.status === f).length})`}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto chat-scroll p-4 space-y-3 bg-sand-50">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-pulse text-sand-400 text-sm">
              Loading metadata...
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-sand-400 text-sm text-center">
            <div>
              <p>No metadata entries yet.</p>
              <p className="text-xs mt-1">
                Chat with the agent to capture experiment metadata.
              </p>
            </div>
          </div>
        ) : (
          filtered.map((entry) => (
            <MetadataCard
              key={entry.id}
              entry={entry}
              onConfirm={handleConfirm}
            />
          ))
        )}
      </div>

      <div className="px-5 py-3 border-t border-sand-200 bg-white text-xs text-sand-400">
        {entries.length} entries | Auto-refreshing every 5s
      </div>
    </div>
  );
}
