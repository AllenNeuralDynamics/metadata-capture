const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

export interface ValidationResults {
  status: 'valid' | 'warnings' | 'errors' | 'pending';
  completeness_score: number;
  errors: { field: string; message: string; severity: string }[];
  warnings: { field: string; message: string; severity: string }[];
  missing_required: string[];
  valid_fields: string[];
}

export interface MetadataEntry {
  id: string;
  subject_id: string;
  session_id: string;
  status: 'draft' | 'confirmed';
  fields: Record<string, unknown>;
  validation: ValidationResults | null;
  created_at: string;
  updated_at: string;
}

const SCHEMA_FIELDS = [
  'subject_json', 'procedures_json', 'data_description_json',
  'instrument_json', 'acquisition_json', 'session_json',
  'processing_json', 'quality_control_json', 'rig_json',
] as const;

/** Transform a raw backend metadata row into the frontend MetadataEntry shape. */
function toMetadataEntry(raw: Record<string, unknown>): MetadataEntry {
  const fields: Record<string, unknown> = {};
  for (const key of SCHEMA_FIELDS) {
    const val = raw[key];
    if (val != null && typeof val === 'object' && Object.keys(val as object).length > 0) {
      const label = key.replace('_json', '');
      fields[label] = val;
    }
  }

  // Try to extract a display label from the subject section.
  // Prefer subject_id, but fall back to the first scalar value if the key was renamed.
  const subjectData = raw.subject_json as Record<string, unknown> | null;
  let subjectLabel: string | undefined = subjectData?.subject_id as string | undefined;
  if (!subjectLabel && subjectData) {
    for (const v of Object.values(subjectData)) {
      if (typeof v === 'string' && v.trim()) { subjectLabel = v; break; }
      if (typeof v === 'number') { subjectLabel = String(v); break; }
    }
  }

  const validation = raw.validation_results_json as ValidationResults | null;

  return {
    id: raw.id as string,
    subject_id: subjectLabel || raw.session_id as string || 'Untitled',
    session_id: raw.session_id as string,
    status: raw.status as 'draft' | 'confirmed',
    fields,
    validation: validation || null,
    created_at: raw.created_at as string,
    updated_at: raw.updated_at as string,
  };
}

export interface Session {
  session_id: string;
  created_at: string;
  last_active: string;
  message_count: number;
  first_message: string | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  onChunk: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  signal?: AbortSignal,
) {
  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        ...(sessionId ? { session_id: sessionId } : {}),
      }),
      signal,
    });

    if (!res.ok) {
      throw new Error(`Chat request failed: ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            onDone();
            return;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.session_id) {
              sessionStorage.setItem('chat_session_id', parsed.session_id);
            }
            // Forward any content-bearing event to the chunk handler
            if (parsed.content || parsed.thinking_start || parsed.thinking ||
                parsed.tool_use_start || parsed.tool_use_input || parsed.block_stop) {
              onChunk(parsed);
            }
          } catch {
            // Plain text chunk — wrap as a content event
            onChunk({ content: data });
          }
        }
      }
    }
    onDone();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      onDone(); // Treat abort as a graceful stop, not an error
      return;
    }
    onError(err as Error);
  }
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
  const data: { role: string; content: string }[] = await res.json();
  return data.map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }));
}

export async function fetchMetadata(): Promise<MetadataEntry[]> {
  const res = await fetch(`${API_BASE}/metadata`);
  if (!res.ok) throw new Error(`Failed to fetch metadata: ${res.status}`);
  const raw: Record<string, unknown>[] = await res.json();
  return raw.map(toMetadataEntry);
}

export async function updateMetadataField(sessionId: string, field: string, value: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${API_BASE}/metadata/${sessionId}/fields`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  });
  if (!res.ok) throw new Error(`Failed to update field: ${res.status}`);
}

export async function confirmMetadata(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/metadata/${id}/confirm`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to confirm metadata: ${res.status}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
}

export async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  return res.json();
}
