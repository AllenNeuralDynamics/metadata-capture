"use client";

// ============================================================================
// VENDORED from anthropics/apps @ f472a1db
//   apps/user-content-renderer/components/renderers/shared/TableView.tsx
//
// This is the file-attachment preview grid from claude.ai (the Excel-style
// table you see when you upload a CSV/XLSX to a chat message). It is NOT
// part of the artifact pipeline upstream — claude.ai has no table artifact
// type — but we use it here for visual parity.
//
// PATCHES (search for "METADATA-CAPTURE PATCH"):
//   1. Added optional `cellRenderer` prop — lets the edit wrapper inject
//      <EditableCell> for editable cells while keeping the visual shell
//      identical to upstream. If absent, behavior is identical to upstream.
//
// To sync: diff against the upstream path above, reapply the single patch.
// ============================================================================

import React, { useCallback, useRef, useState } from "react";

const MAX_VISIBLE_ROWS = 100;
const MAX_VISIBLE_COLS = 20;
const MIN_COL_WIDTH = 120;
const ROW_HEADER_WIDTH = 50;

export interface CellData {
  value: string | null;
  formula?: string;
}

// METADATA-CAPTURE PATCH: render-prop for cell injection. Receives the cell
// coordinates + the default <td> the upstream component would have rendered.
// Return the default to get upstream behavior, or return a custom <td>.
export type CellRenderer = (
  row: number,
  col: number,
  value: string | null,
  defaultTd: React.ReactElement,
) => React.ReactElement;

interface TableViewProps {
  sheetName: string;
  data: (string | null | CellData)[][];
  selectedCell: { row: number; col: number } | null;
  onCellSelect: (cell: { row: number; col: number } | null) => void;
  isFirstRowHeader?: boolean;
  formulaBar?: boolean;
  // METADATA-CAPTURE PATCH
  cellRenderer?: CellRenderer;
}

const isCellData = (cell: string | null | CellData): cell is CellData => {
  return cell !== null && typeof cell === "object" && "value" in cell;
};

const getCellValue = (cell: string | null | CellData): string | null => {
  if (isCellData(cell)) {
    return cell.value;
  }
  return cell;
};

const getCellFormula = (cell: string | null | CellData): string | undefined => {
  if (isCellData(cell)) {
    return cell.formula;
  }
  return undefined;
};

function TableViewComponent({
  sheetName: _sheetName,
  data,
  selectedCell,
  onCellSelect,
  isFirstRowHeader = false,
  formulaBar = false,
  cellRenderer, // METADATA-CAPTURE PATCH
}: TableViewProps): React.ReactElement {
  const visibleCols = Math.min(
    Math.max(...data.map((row) => row?.length || 0)),
    MAX_VISIBLE_COLS,
  );

  const [columnWidths, setColumnWidths] = useState<number[]>(() =>
    Array<number>(visibleCols).fill(MIN_COL_WIDTH),
  );
  const [isResizing, setIsResizing] = useState(false);
  const resizeStartX = useRef<number>(0);
  const resizeStartWidth = useRef<number>(0);
  const resizingColumnRef = useRef<number | null>(null);

  const columnToLetter = useCallback((col: number): string => {
    let letter = "";
    while (col >= 0) {
      letter = String.fromCharCode((col % 26) + 65) + letter;
      col = Math.floor(col / 26) - 1;
    }
    return letter;
  }, []);

  const formatCellValue = useCallback((value: string | null): string => {
    if (value === null || value === undefined) return "";
    return String(value);
  }, []);

  const getFormulaBarContent = useCallback(
    (cell: string | null | CellData): string => {
      const formula = getCellFormula(cell);
      if (formula) {
        return `=${formula}`;
      }
      const value = getCellValue(cell);
      return formatCellValue(value);
    },
    [formatCellValue],
  );

  const handleResizeMove = useCallback((e: MouseEvent) => {
    const deltaX = e.clientX - resizeStartX.current;
    const newWidth = Math.max(MIN_COL_WIDTH, resizeStartWidth.current + deltaX);

    setColumnWidths((prev) => {
      const updated = [...prev];
      if (resizingColumnRef.current !== null) {
        updated[resizingColumnRef.current] = newWidth;
      }
      return updated;
    });
  }, []);

  const handleResizeEnd = useCallback(() => {
    document.removeEventListener("mousemove", handleResizeMove);
    document.removeEventListener("mouseup", handleResizeEnd);
    resizingColumnRef.current = null;
    setIsResizing(false);
  }, [handleResizeMove]);

  const handleResizeStart = useCallback(
    (e: React.MouseEvent, colIndex: number) => {
      e.preventDefault();
      e.stopPropagation();
      setColumnWidths((prev) => {
        resizeStartWidth.current = prev[colIndex];
        return prev;
      });
      resizeStartX.current = e.clientX;
      resizingColumnRef.current = colIndex;
      setIsResizing(true);

      document.addEventListener("mousemove", handleResizeMove);
      document.addEventListener("mouseup", handleResizeEnd);
    },
    [handleResizeMove, handleResizeEnd],
  );

  if (!data.length) {
    return (
      <div className="flex items-center justify-center min-h-[600px] bg-gray-50 rounded-lg">
        <p className="text-gray-500">No data available</p>
      </div>
    );
  }

  return (
    <div
      className="flex-1 min-h-0 w-full bg-gray-50"
      style={{ cursor: isResizing ? "col-resize" : undefined }}
    >
      <div className="flex flex-col h-full bg-white rounded-sm border border-gray-200 overflow-hidden">
        {/* Formula Bar (optional) */}
        {formulaBar && (
          <div className="bg-white border-b border-gray-300 px-3 py-2 min-h-[44px] flex items-center">
            <div className="text-sm text-gray-700 font-mono">
              {selectedCell && data[selectedCell.row]?.[selectedCell.col] ? (
                getFormulaBarContent(data[selectedCell.row]?.[selectedCell.col])
              ) : (
                <span className="text-gray-400">
                  Select a cell to view its content
                </span>
              )}
            </div>
          </div>
        )}

        {/* Grid */}
        <div className="flex-1 overflow-auto relative bg-gray-50">
          <table className="border-collapse" style={{ tableLayout: "fixed" }}>
            <thead className="sticky top-0 z-20 bg-gray-200">
              <tr>
                <th
                  className="sticky left-0 z-30 border-r border-b border-gray-300 bg-gray-300"
                  style={{
                    width: `${ROW_HEADER_WIDTH}px`,
                    minWidth: `${ROW_HEADER_WIDTH}px`,
                  }}
                />
                {Array.from({ length: visibleCols }).map((_, i) => (
                  <th
                    key={i}
                    className="relative border-r border-b border-gray-300 bg-gray-200 px-4 py-2 text-xs font-semibold text-gray-700"
                    style={{
                      width: `${columnWidths[i]}px`,
                      minWidth: `${columnWidths[i]}px`,
                    }}
                  >
                    {columnToLetter(i)}
                    <div
                      className="absolute top-0 -right-1 w-3 h-full cursor-col-resize hover:bg-blue-400 active:bg-blue-500 z-10"
                      onMouseDown={(e) => handleResizeStart(e, i)}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.slice(0, MAX_VISIBLE_ROWS).map((row, rowIndex) => {
                const isHeader = isFirstRowHeader && rowIndex === 0;
                return (
                  <tr key={rowIndex}>
                    <td
                      className="sticky left-0 z-10 border-r border-b border-gray-300 bg-gray-200 text-center text-xs font-semibold text-gray-700"
                      style={{
                        width: `${ROW_HEADER_WIDTH}px`,
                        minWidth: `${ROW_HEADER_WIDTH}px`,
                      }}
                    >
                      {rowIndex + 1}
                    </td>
                    {Array.from({
                      length: visibleCols,
                    }).map((_, colIndex) => {
                      const cell = row?.[colIndex];
                      const cellValue = getCellValue(cell);
                      const cellFormula = getCellFormula(cell);
                      const isSelected =
                        selectedCell?.row === rowIndex &&
                        selectedCell?.col === colIndex;
                      const defaultTd = (
                        <td
                          key={colIndex}
                          onClick={() =>
                            onCellSelect({ row: rowIndex, col: colIndex })
                          }
                          className={`border border-gray-300 px-2 py-1 text-sm cursor-cell ${
                            isHeader ? "font-semibold bg-gray-100" : ""
                          } ${
                            isSelected
                              ? "bg-blue-50 outline outline-2 outline-blue-500"
                              : isHeader
                                ? ""
                                : "hover:bg-gray-50"
                          }`}
                          style={{
                            width: `${columnWidths[colIndex]}px`,
                            minWidth: `${columnWidths[colIndex]}px`,
                            maxWidth: `${columnWidths[colIndex]}px`,
                          }}
                        >
                          {cellFormula && (!cellValue || cellValue === "") ? (
                            <span className="text-gray-400 italic">
                              ={cellFormula}
                            </span>
                          ) : (
                            formatCellValue(cellValue)
                          )}
                        </td>
                      );
                      // METADATA-CAPTURE PATCH: let wrapper inject editable cell.
                      // When cellRenderer is undefined this collapses to upstream.
                      return cellRenderer
                        ? cellRenderer(rowIndex, colIndex, cellValue, defaultTd)
                        : defaultTd;
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export const TableView = React.memo(TableViewComponent);
