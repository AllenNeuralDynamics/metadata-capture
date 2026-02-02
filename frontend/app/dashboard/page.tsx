'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { fetchMetadata, confirmMetadata, updateMetadataField, MetadataEntry } from '../lib/api';
import Header from '../components/Header';

const SCHEMA_SECTIONS = [
  { key: 'subject', label: 'Subject' },
  { key: 'procedures', label: 'Procedures' },
  { key: 'data_description', label: 'Data Description' },
  { key: 'instrument', label: 'Instrument' },
  { key: 'acquisition', label: 'Acquisition' },
  { key: 'session', label: 'Session' },
  { key: 'processing', label: 'Processing' },
  { key: 'quality_control', label: 'Quality Control' },
  { key: 'rig', label: 'Rig' },
] as const;

/** Known fields per section — shown as placeholders when not yet filled. */
const SECTION_FIELD_SCHEMAS: Record<string, { label: string; path: string[] }[]> = {
  subject: [
    { label: 'Subject ID', path: ['subject_id'] },
    { label: 'Species', path: ['species', 'name'] },
    { label: 'Sex', path: ['sex'] },
    { label: 'Age', path: ['age'] },
    { label: 'Genotype', path: ['genotype'] },
  ],
  procedures: [
    { label: 'Procedure Type', path: ['procedure_type'] },
    { label: 'Notes', path: ['notes'] },
  ],
  data_description: [
    { label: 'Project Name', path: ['project_name'] },
    { label: 'Institution', path: ['institution'] },
  ],
  session: [
    { label: 'Start Time', path: ['session_start_time'] },
    { label: 'End Time', path: ['session_end_time'] },
    { label: 'Notes', path: ['notes'] },
  ],
  instrument: [
    { label: 'Instrument ID', path: ['instrument_id'] },
  ],
  acquisition: [
    { label: 'Acquisition Number', path: ['acquisition_number'] },
    { label: 'Notes', path: ['notes'] },
  ],
  processing: [
    { label: 'Pipeline', path: ['pipeline'] },
    { label: 'Notes', path: ['notes'] },
  ],
  quality_control: [
    { label: 'Status', path: ['status'] },
    { label: 'Notes', path: ['notes'] },
  ],
  rig: [
    { label: 'Rig ID', path: ['rig_id'] },
  ],
};

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: 'bg-brand-orange-100 text-brand-orange-600 border-brand-orange-500/20',
    validated: 'bg-brand-violet-500/10 text-brand-violet-600 border-brand-violet-500/20',
    confirmed: 'bg-brand-aqua-500/10 text-brand-aqua-700 border-brand-aqua-500/20',
    error: 'bg-brand-magenta-100 text-brand-magenta-600 border-brand-magenta-200',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[status] || styles.draft}`}>
      {status}
    </span>
  );
}

interface FlatField {
  label: string;
  value: string;
  path: string[];
  editable: boolean;
}

/** Flatten a nested object into label/value/path triples for inline editing. */
function flattenFields(obj: unknown, prefix = '', path: string[] = []): FlatField[] {
  if (obj == null) return [];
  if (typeof obj !== 'object') return [{ label: prefix || 'value', value: String(obj), path, editable: true }];
  const entries: FlatField[] = [];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const label = prefix ? `${prefix} > ${k.replace(/_/g, ' ')}` : k.replace(/_/g, ' ');
    const fieldPath = [...path, k];
    if (v != null && typeof v === 'object' && !Array.isArray(v)) {
      const nested = v as Record<string, unknown>;
      if (Object.keys(nested).length === 1 && 'name' in nested) {
        entries.push({ label, value: String(nested.name), path: [...fieldPath, 'name'], editable: true });
      } else {
        entries.push(...flattenFields(v, label, fieldPath));
      }
    } else if (Array.isArray(v)) {
      entries.push({
        label,
        value: v.map((item) => (typeof item === 'object' ? (item as Record<string, unknown>).name ?? JSON.stringify(item) : String(item))).join(', '),
        path: fieldPath,
        editable: false,
      });
    } else {
      entries.push({ label, value: String(v), path: fieldPath, editable: true });
    }
  }
  return entries;
}

/** Deep-clone and set a value at a nested path. */
function deepSet(obj: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  const result = { ...obj };
  if (path.length === 1) { result[path[0]] = value; return result; }
  const [head, ...tail] = path;
  result[head] = deepSet((result[head] || {}) as Record<string, unknown>, tail, value);
  return result;
}

/** Rename a top-level key, preserving insertion order. */
function renameKey(obj: Record<string, unknown>, oldKey: string, newKey: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    result[k === oldKey ? newKey : k] = v;
  }
  return result;
}

/** Remove a top-level key from an object. */
function deleteKey(obj: Record<string, unknown>, key: string): Record<string, unknown> {
  const { [key]: _, ...rest } = obj;
  return rest;
}

function EditableValue({
  field,
  sectionValue,
  sessionId,
  sectionKey,
  onSaved,
}: {
  field: FlatField;
  sectionValue: Record<string, unknown>;
  sessionId: string;
  sectionKey: string;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(field.value);
  const [editingLabel, setEditingLabel] = useState(false);
  const [labelText, setLabelText] = useState(field.path[0]);
  // For placeholders: track a locally-renamed path so the value saves under the new key
  const [currentPath, setCurrentPath] = useState(field.path);
  const [displayLabel, setDisplayLabel] = useState(field.label);

  const save = async () => {
    setEditing(false);
    if (text === field.value) return;
    if (text === '') return;
    try {
      const updated = deepSet(sectionValue, currentPath, text);
      await updateMetadataField(sessionId, sectionKey, updated);
      onSaved();
    } catch {
      // revert on next reload
    }
  };

  const handleDelete = async () => {
    try {
      const updated = deleteKey(sectionValue, currentPath[0]);
      await updateMetadataField(sessionId, sectionKey, updated);
      onSaved();
    } catch {
      // revert on next reload
    }
  };

  const saveLabel = async () => {
    setEditingLabel(false);
    const newKey = labelText.trim().replace(/\s+/g, '_');
    const oldKey = currentPath[0];
    if (!newKey || newKey === oldKey) return;

    if (field.value === '') {
      // Placeholder: update path locally so value saves under the new key
      setCurrentPath([newKey, ...currentPath.slice(1)]);
      setDisplayLabel(labelText.trim());
    } else {
      // Existing field: rename on the backend
      try {
        const renamed = renameKey(sectionValue, oldKey, newKey);
        await updateMetadataField(sessionId, sectionKey, renamed);
        onSaved();
      } catch {
        // revert on next reload
      }
    }
  };

  const renderLabel = () => {
    if (editingLabel) {
      return (
        <input
          autoFocus
          value={labelText}
          onChange={(e) => setLabelText(e.target.value)}
          onBlur={saveLabel}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur(); }
            if (e.key === 'Escape') { setEditingLabel(false); setLabelText(currentPath[0]); }
          }}
          className="text-sand-400 shrink-0 w-36 border-b border-brand-fig/50 bg-transparent py-0.5
                     focus:outline-none focus:border-brand-fig capitalize"
        />
      );
    }
    return (
      <span
        className="text-sand-400 shrink-0 w-36 truncate capitalize cursor-pointer hover:text-brand-fig"
        onClick={(e) => { e.stopPropagation(); setLabelText(currentPath[0]); setEditingLabel(true); }}
      >
        {displayLabel}:
      </span>
    );
  };

  if (editing) {
    return (
      <div className="flex text-xs gap-2 items-center">
        {renderLabel()}
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur(); }
            if (e.key === 'Escape') { setEditing(false); setText(field.value); }
          }}
          className="text-sand-700 flex-1 border-b border-brand-fig/50 bg-transparent py-0.5
                     focus:outline-none focus:border-brand-fig"
        />
      </div>
    );
  }

  // Empty placeholder — click to add value
  if (field.value === '') {
    return (
      <div
        className="flex text-xs gap-2 rounded px-1 -mx-1 py-0.5 cursor-pointer hover:bg-sand-50 group"
        onClick={() => { setText(''); setEditing(true); }}
      >
        {renderLabel()}
        <span className="text-sand-300 italic group-hover:text-sand-400">click to add</span>
      </div>
    );
  }

  return (
    <div
      className={`flex text-xs gap-2 items-center rounded px-1 -mx-1 py-0.5 group ${field.editable ? 'cursor-pointer hover:bg-sand-50' : ''}`}
      onClick={() => { if (field.editable) { setText(field.value); setEditing(true); } }}
    >
      {renderLabel()}
      <span className="text-sand-700 flex-1">{field.value}</span>
      {field.editable && (
        <button
          onClick={(e) => { e.stopPropagation(); handleDelete(); }}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-sand-300 hover:text-brand-orange-600 shrink-0"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2M10 11v6M14 11v6" />
          </svg>
        </button>
      )}
    </div>
  );
}

/** Row for adding a brand-new field to a section. */
function AddFieldRow({
  sectionValue,
  sessionId,
  sectionKey,
  onSaved,
}: {
  sectionValue: Record<string, unknown>;
  sessionId: string;
  sectionKey: string;
  onSaved: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const valueRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    const cleanKey = key.trim().replace(/\s+/g, '_');
    if (!cleanKey || !value.trim()) { setAdding(false); setKey(''); setValue(''); return; }
    try {
      const updated = { ...sectionValue, [cleanKey]: value.trim() };
      await updateMetadataField(sessionId, sectionKey, updated);
      onSaved();
    } catch {
      // fail silently
    }
    setKey('');
    setValue('');
    setAdding(false);
  };

  if (!adding) {
    return (
      <button
        onClick={() => setAdding(true)}
        className="text-xs text-sand-400 hover:text-brand-fig flex items-center gap-1 pt-1.5 transition-colors"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" viewBox="0 0 24 24">
          <path d="M12 4v16m8-8H4" />
        </svg>
        Add field
      </button>
    );
  }

  return (
    <div className="flex text-xs gap-2 items-center pt-1.5">
      <input
        autoFocus
        placeholder="field name"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Tab') { e.preventDefault(); valueRef.current?.focus(); }
          if (e.key === 'Escape') { setAdding(false); setKey(''); setValue(''); }
        }}
        className="w-36 shrink-0 border-b border-sand-300 bg-transparent py-0.5
                   focus:outline-none focus:border-brand-fig placeholder:text-sand-300"
      />
      <span className="text-sand-400">:</span>
      <input
        ref={valueRef}
        placeholder="value"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); handleSave(); }
          if (e.key === 'Escape') { setAdding(false); setKey(''); setValue(''); }
        }}
        className="flex-1 border-b border-sand-300 bg-transparent py-0.5 text-sand-700
                   focus:outline-none focus:border-brand-fig placeholder:text-sand-300"
      />
    </div>
  );
}

function SectionEditor({
  sessionId,
  sectionKey,
  label,
  value,
  onSaved,
}: {
  sessionId: string;
  sectionKey: string;
  label: string;
  value: unknown;
  onSaved: () => void;
}) {
  const isFilled = value != null;
  const sectionObj = (value || {}) as Record<string, unknown>;

  const schemaFields = SECTION_FIELD_SCHEMAS[sectionKey] || [];

  // Existing fields from the live data, with schema labels applied where available
  const schemaLabelMap = new Map(schemaFields.map((sf) => [sf.path.join('.'), sf.label]));
  const existingFields = isFilled
    ? flattenFields(value).map((f) => ({ ...f, label: schemaLabelMap.get(f.path.join('.')) || f.label }))
    : [];
  const existingPaths = new Set(existingFields.map((f) => f.path.join('.')));
  const missingFields: FlatField[] = schemaFields
    .filter((sf) => !existingPaths.has(sf.path.join('.')))
    .map((sf) => ({ label: sf.label, value: '', path: sf.path, editable: true }));

  const allFields = [...existingFields, ...missingFields];

  return (
    <div className="bg-white rounded-lg border border-sand-200 p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-2 h-2 rounded-full ${isFilled ? 'bg-brand-aqua-500' : 'bg-sand-300'}`} />
        <h5 className="text-sm font-medium text-sand-800">{label}</h5>
      </div>
      <div className="space-y-0.5">
        {allFields.map((field) => (
          <EditableValue
            key={field.path.join('.')}
            field={field}
            sectionValue={sectionObj}
            sessionId={sessionId}
            sectionKey={sectionKey}
            onSaved={onSaved}
          />
        ))}
        <AddFieldRow
          sectionValue={sectionObj}
          sessionId={sessionId}
          sectionKey={sectionKey}
          onSaved={onSaved}
        />
      </div>
    </div>
  );
}

function ExpandedRow({ entry, onConfirm, onFieldSaved }: { entry: MetadataEntry; onConfirm: (id: string) => void; onFieldSaved: () => void }) {
  return (
    <tr>
      <td colSpan={5} className="px-6 py-4 bg-sand-50 border-b border-sand-200">
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {SCHEMA_SECTIONS.map((section) => (
              <SectionEditor
                key={section.key}
                sessionId={entry.session_id}
                sectionKey={section.key}
                label={section.label}
                value={(entry.fields || {})[section.key] ?? null}
                onSaved={onFieldSaved}
              />
            ))}
          </div>

          {entry.status === 'draft' && (
            <div className="flex gap-2 pt-2 border-t border-sand-200">
              <button
                onClick={() => onConfirm(entry.session_id)}
                className="px-4 py-2 bg-brand-aqua-500 text-white text-sm font-medium rounded-lg hover:bg-brand-aqua-700 transition-colors"
              >
                Confirm Metadata
              </button>
              <Link
                href="/"
                className="px-4 py-2 bg-sand-100 text-sand-600 text-sm font-medium rounded-lg hover:bg-sand-200 transition-colors border border-sand-200"
              >
                Continue Capture
              </Link>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function DashboardPage() {
  const [entries, setEntries] = useState<MetadataEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await fetchMetadata();
      setEntries(data);
    } catch {
      // API not available
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  // Auto-expand entry if navigated via hash (e.g. /dashboard#<session_id>)
  useEffect(() => {
    if (entries.length === 0) return;
    const hash = window.location.hash.slice(1);
    if (hash) setExpandedId(hash);
  }, [entries]);

  // Scroll the expanded row into view whenever expandedId changes
  useEffect(() => {
    if (!expandedId) return;
    // Wait one frame for the ExpandedRow to render
    requestAnimationFrame(() => {
      document.getElementById(`row-${expandedId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [expandedId]);

  const handleConfirm = async (sessionId: string) => {
    try {
      await confirmMetadata(sessionId);
      load();
    } catch (err) {
      console.error('Failed to confirm:', err);
    }
  };

  const filtered = entries.filter((e) => {
    if (filter !== 'all' && e.status !== filter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        e.subject_id?.toLowerCase().includes(s) ||
        e.session_id?.toLowerCase().includes(s) ||
        JSON.stringify(e.fields).toLowerCase().includes(s)
      );
    }
    return true;
  });

  const counts = {
    all: entries.length,
    draft: entries.filter((e) => e.status === 'draft').length,
    confirmed: entries.filter((e) => e.status === 'confirmed').length,
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <Header />

      {/* Filters */}
      <div className="bg-white border-b border-sand-200 px-6 py-3">
        <div className="flex items-center gap-4">
          <div className="flex gap-1">
            {(['all', 'draft', 'confirmed'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  filter === f
                    ? 'bg-sand-800 text-white'
                    : 'bg-sand-100 text-sand-500 hover:bg-sand-200'
                }`}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f]})
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <input
            type="text"
            placeholder="Search by subject, session..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64 px-3 py-1.5 text-sm border border-sand-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-fig/30 focus:border-brand-fig/50"
          />
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-64 text-sand-400">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-sand-400">
            <p className="text-lg">No metadata entries found</p>
            <p className="text-sm mt-1">Start a chat to capture experiment metadata</p>
          </div>
        ) : (
          <table className="w-full bg-white rounded-xl border border-sand-200 overflow-hidden">
            <thead>
              <tr className="bg-sand-50 border-b border-sand-200">
                <th className="text-left px-6 py-3 text-xs font-semibold text-sand-500 uppercase tracking-wider">Subject</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-sand-500 uppercase tracking-wider">Fields</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-sand-500 uppercase tracking-wider">Status</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-sand-500 uppercase tracking-wider">Created</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-sand-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <>
                  <tr
                    key={entry.id}
                    id={`row-${entry.session_id}`}
                    onClick={() => setExpandedId(expandedId === entry.session_id ? null : entry.session_id)}
                    className="border-b border-sand-100 hover:bg-sand-50 cursor-pointer transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-sand-800">{entry.subject_id}</div>
                      <div className="text-xs text-sand-400">{new Date(entry.created_at).toLocaleDateString()}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {entry.fields && Object.keys(entry.fields).length > 0 ? (
                          Object.keys(entry.fields).map((key) => (
                            <span key={key} className="inline-flex items-center px-2 py-0.5 rounded bg-brand-coral/30 text-brand-fig text-xs">
                              {key}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-sand-400 italic">No fields</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={entry.status} />
                    </td>
                    <td className="px-6 py-4 text-sm text-sand-500">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <button className="text-xs text-brand-fig hover:text-brand-magenta-800 font-medium">
                        {expandedId === entry.session_id ? 'Collapse' : 'Expand'}
                      </button>
                    </td>
                  </tr>
                  {expandedId === entry.session_id && (
                    <ExpandedRow key={`${entry.session_id}-expanded`} entry={entry} onConfirm={handleConfirm} onFieldSaved={load} />
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
