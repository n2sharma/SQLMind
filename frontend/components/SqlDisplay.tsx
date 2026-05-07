"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";

interface SqlDisplayProps {
  sql: string;
}

export default function SqlDisplay({ sql }: SqlDisplayProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const keywords =
    /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|AS|AND|OR|NOT|IN|IS|NULL|COUNT|SUM|AVG|MIN|MAX|DISTINCT)\b/gi;

  // Basic SQL syntax highlighting with spans
  const highlighted = sql
    .split("\n")
    .map((line) =>
      line.replace(
        keywords,
        '<span style="color:#60a5fa;font-weight:600">$1</span>'
      )
    )
    .join("\n");

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <span className="text-xs text-gray-500 font-medium">Generated SQL</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
        >
          {copied ? (
            <Check size={12} className="text-green-400" />
          ) : (
            <Copy size={12} />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="px-4 py-3 text-xs overflow-x-auto">
        <code
          dangerouslySetInnerHTML={{ __html: highlighted }}
          className="text-gray-300 font-mono leading-relaxed"
        />
      </pre>
    </div>
  );
}
