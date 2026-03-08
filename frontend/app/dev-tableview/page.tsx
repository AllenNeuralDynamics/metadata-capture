'use client';

// Dev-only visual harness for EditableTableView. No backend needed.
// Route: /dev-tableview
//
// Renders three variants side-by-side so we can screenshot-compare
// against claude.ai's file-preview grid:
//   1. read-only (upload-style) — should look IDENTICAL to claude.ai
//   2. editable (table artifact with record_id) — same shell + edit layer
//   3. editable with a missing-record row — verify readonly fallback styling

import { useState } from 'react';
import EditableTableView from '../components/EditableTableView';

const COLUMNS = ['record_id', 'subject_id', 'species', 'sex', 'genotype'];
const ROWS = [
  ['rec-001', '4528', 'Mus musculus', 'Male', 'Pvalb-IRES-Cre/wt'],
  ['rec-002', '4529', 'Mus musculus', 'Female', 'Sst-IRES-Cre/wt'],
  ['rec-003', '4530', 'Rattus norvegicus', 'Male', 'wt/wt'],
  ['rec-004', '4531', 'Mus musculus', 'Female', 'Vip-IRES-Cre/wt'],
  ['rec-005', '4532', 'Mus musculus', 'Male', 'Pvalb-IRES-Cre/wt'],
];
const ENUMS = {
  species: ['Mus musculus', 'Rattus norvegicus', 'Macaca mulatta'],
  sex: ['Male', 'Female'],
};

export default function DevTableViewPage() {
  const [log, setLog] = useState<string[]>([]);

  const handleCommit = async (recordId: string, column: string, value: string) => {
    setLog((l) => [...l, `PATCH ${recordId} ${column}="${value}"`]);
    await new Promise((r) => setTimeout(r, 300)); // simulate network
    if (value === 'FAIL') throw new Error('Simulated 400 — bad value');
  };

  return (
    <div className="p-8 bg-gray-100 min-h-screen space-y-8">
      <h1 className="text-2xl font-bold">TableView visual harness</h1>

      {/* Read-only — the "does it look like claude.ai" variant */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Read-only (upload preview)</h2>
        <div className="h-96 bg-white rounded-lg shadow">
          <EditableTableView
            columns={COLUMNS}
            rows={ROWS}
            sheetName="test_subjects.csv"
          />
        </div>
      </section>

      {/* Editable — table artifact with record_id */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Editable (formulaBar on, species/sex are enum dropdowns)</h2>
        <div className="h-96 bg-white rounded-lg shadow">
          <EditableTableView
            columns={COLUMNS}
            rows={ROWS}
            recordIdColumn={0}
            enums={ENUMS}
            onCellCommit={handleCommit}
          />
        </div>
      </section>

      {/* Editable with a missing-record row */}
      <section>
        <h2 className="text-lg font-semibold mb-2">Editable with missing row (row 3 = rec-003 not found → readonly)</h2>
        <div className="h-96 bg-white rounded-lg shadow">
          <EditableTableView
            columns={COLUMNS}
            rows={ROWS}
            recordIdColumn={0}
            enums={ENUMS}
            missingRows={new Set([2])}
            onCellCommit={handleCommit}
          />
        </div>
      </section>

      {/* Commit log */}
      <section>
        <h2 className="text-sm font-semibold mb-1">Commit log</h2>
        <pre className="text-xs bg-white p-3 rounded border border-gray-200 min-h-[60px]">
          {log.length ? log.join('\n') : '(try typing "FAIL" into a cell to test error display)'}
        </pre>
      </section>
    </div>
  );
}
