"use client";
import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface ResultTableProps {
  rows: Record<string, unknown>[];
  rowCount: number;
}

const PAGE_SIZE = 10;

export default function ResultTable({ rows, rowCount }: ResultTableProps) {
  const [page, setPage] = useState(0);

  if (!rows || rows.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-8 text-center text-gray-500 text-sm">
        No rows returned
      </div>
    );
  }

  const columns = Object.keys(rows[0]);
  const totalPages = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <span className="text-xs text-gray-500 font-medium">
          {rowCount} row{rowCount !== 1 ? "s" : ""} returned
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="disabled:opacity-30 hover:text-gray-200 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <span>
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              className="disabled:opacity-30 hover:text-gray-200 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-2 text-left text-gray-400 font-medium whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-2 text-gray-300 whitespace-nowrap"
                  >
                    {row[col] === null ? (
                      <span className="text-gray-600 italic">null</span>
                    ) : typeof row[col] === "number" ? (
                      <span className="text-yellow-400 font-mono">
                        {typeof row[col] === "number" &&
                        !Number.isInteger(row[col])
                          ? (row[col] as number).toFixed(2)
                          : String(row[col])}
                      </span>
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
