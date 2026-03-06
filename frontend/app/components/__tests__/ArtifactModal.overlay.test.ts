/**
 * Overlay logic for record-bound table artifacts.
 *
 * Artifacts are immutable snapshots. When a table has a record_id column,
 * we fetch live records and overlay their current data_json onto the snapshot
 * so the user sees truth, not stale data. These functions are the core of that.
 */
import { describe, it, expect } from 'vitest';
import { flattenForDisplay, overlayRows } from '../ArtifactModal';

describe('flattenForDisplay', () => {
  it('passes strings through', () => {
    expect(flattenForDisplay('Pvalb-IRES-Cre/wt')).toBe('Pvalb-IRES-Cre/wt');
  });

  it('passes numbers through', () => {
    expect(flattenForDisplay(42)).toBe(42);
  });

  it('returns null for null/undefined', () => {
    expect(flattenForDisplay(null)).toBeNull();
    expect(flattenForDisplay(undefined)).toBeNull();
  });

  it('flattens species-shaped dicts to .name — the core P0 case', () => {
    // data_json.species is {name, registry, registry_identifier}.
    // The artifact shows it as a string. Overlay must flatten the dict back
    // to what the dropdown expects (the enum value).
    expect(
      flattenForDisplay({
        name: 'Rattus norvegicus',
        registry: 'NCBI',
        registry_identifier: 'NCBI:txid10116',
      }),
    ).toBe('Rattus norvegicus');
  });

  it('flattens modality-shaped dicts to .abbreviation when no .name', () => {
    expect(flattenForDisplay({ abbreviation: 'ecephys' })).toBe('ecephys');
  });

  it('prefers .name over .abbreviation when both present', () => {
    expect(flattenForDisplay({ name: 'N', abbreviation: 'A' })).toBe('N');
  });

  it('JSON-stringifies objects with neither name nor abbreviation', () => {
    expect(flattenForDisplay({ x: 1 })).toBe('{"x":1}');
  });

  it('stringifies other primitives', () => {
    expect(flattenForDisplay(true)).toBe('true');
  });
});

describe('overlayRows', () => {
  const COLS = ['record_id', 'subject_id', 'species', 'sex'];
  const RID_COL = 0;

  it('replaces snapshot cells with live data where the column matches', () => {
    const snapshot = [['rec-1', '9999', 'Mus musculus', 'Male']];
    const live = new Map([
      ['rec-1', { subject_id: '9999', species: { name: 'Rattus norvegicus' }, sex: 'Female' }],
    ]);

    const out = overlayRows({ columns: COLS, rows: snapshot }, RID_COL, live);

    // species dict → flattened to .name; snapshot completely overwritten where live has it
    expect(out[0]).toEqual(['rec-1', '9999', 'Rattus norvegicus', 'Female']);
  });

  it('falls back to snapshot for rows with no live entry (missing/hallucinated IDs)', () => {
    const snapshot = [
      ['rec-real', '1', 'Mus musculus', 'Male'],
      ['rec-fake', '2', '???', '???'],
    ];
    const live = new Map([['rec-real', { sex: 'Female' }]]);

    const out = overlayRows({ columns: COLS, rows: snapshot }, RID_COL, live);

    expect(out[0][3]).toBe('Female'); // overlaid
    expect(out[1]).toEqual(['rec-fake', '2', '???', '???']); // snapshot untouched
  });

  it('keeps snapshot value for columns not present in live data_json', () => {
    // Agent might include a computed column the record doesn't store.
    const snapshot = [['rec-1', '9999', 'Mus musculus', 'Male']];
    const live = new Map([['rec-1', { subject_id: '9999' }]]); // no species, no sex

    const out = overlayRows({ columns: COLS, rows: snapshot }, RID_COL, live);

    expect(out[0][1]).toBe('9999'); // overlaid (same value, but from live)
    expect(out[0][2]).toBe('Mus musculus'); // snapshot fallback — live.species is undefined
    expect(out[0][3]).toBe('Male'); // snapshot fallback
  });

  it('never touches the record_id column', () => {
    const snapshot = [['rec-1', '9999', 'X', 'Y']];
    // Pathological: live data somehow has a record_id field. Don't overlay it.
    const live = new Map([['rec-1', { record_id: 'CORRUPTED', subject_id: '9999' }]]);

    const out = overlayRows({ columns: COLS, rows: snapshot }, RID_COL, live);

    expect(out[0][0]).toBe('rec-1');
  });

  it('handles live value of null — overlays it (null is a legit value, not absence)', () => {
    // undefined means "not in live data" → snapshot fallback.
    // null means "live data says this field is null" → show null.
    const snapshot = [['rec-1', '9999', 'Mus musculus', 'Male']];
    const live = new Map([['rec-1', { sex: null }]]);

    const out = overlayRows({ columns: COLS, rows: snapshot }, RID_COL, live);

    expect(out[0][3]).toBeNull();
  });

  it('handles empty inputs', () => {
    expect(overlayRows({ columns: COLS, rows: [] }, RID_COL, new Map())).toEqual([]);
  });
});
