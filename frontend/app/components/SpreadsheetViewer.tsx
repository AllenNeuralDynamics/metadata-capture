// Thin re-export. The implementation lives in EditableTableView, which wraps
// the vendored claude.ai TableView (vendor/TableView.tsx).
//
// This file exists to preserve the import path ArtifactModal expects, and
// to give tests a stable place to import EditableCell from.

export { default, EditableCell } from './EditableTableView';
export type { EditableTableViewProps as SpreadsheetViewerProps } from './EditableTableView';
