"use client";
import { useState, useRef } from "react";
import { Database, Zap } from "lucide-react";
import QueryInput from "@/components/QueryInput";
import StreamStatus, { StreamEvent } from "@/components/StreamStatus";
import SqlDisplay from "@/components/SqlDisplay";
import ResultTable from "@/components/ResultTable";

interface QueryResult {
  sql: string;
  rows: Record<string, unknown>[];
  row_count: number;
  explanation: string;
  tokens_used: number;
  execution_time_ms: number;
  retry_count: number;
}

interface QueryEntry {
  question: string;
  result?: QueryResult;
  error?: string;
  events: StreamEvent[];
  isLoading: boolean;
}

const BACKEND = "http://localhost:8000";

export default function Home() {
  const [entries, setEntries] = useState<QueryEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const handleSubmit = (question: string) => {
    // Close any existing stream
    if (esRef.current) {
      esRef.current.close();
    }

    const newEntry: QueryEntry = {
      question,
      events: [],
      isLoading: true,
    };

    setEntries((prev) => [newEntry, ...prev]);
    setIsLoading(true);

    const url = `${BACKEND}/api/query/stream?question=${encodeURIComponent(
      question
    )}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      const event: StreamEvent & QueryResult = JSON.parse(e.data);

      if (event.type === "complete") {
        setEntries((prev) => {
          const updated = [...prev];
          updated[0] = {
            ...updated[0],
            result: {
              sql: event.sql,
              rows: event.rows,
              row_count: event.row_count,
              explanation: event.explanation,
              tokens_used: event.tokens_used,
              execution_time_ms: event.execution_time_ms,
              retry_count: event.retry_count,
            },
            events: [...updated[0].events, event],
            isLoading: false,
          };
          return updated;
        });
        setIsLoading(false);
        es.close();
      } else if (event.type === "error") {
        setEntries((prev) => {
          const updated = [...prev];
          updated[0] = {
            ...updated[0],
            error: event.message,
            events: [...updated[0].events, event],
            isLoading: false,
          };
          return updated;
        });
        setIsLoading(false);
        es.close();
      } else {
        // Status/progress event — append to events
        setEntries((prev) => {
          const updated = [...prev];
          updated[0] = {
            ...updated[0],
            events: [...updated[0].events, event],
          };
          return updated;
        });
      }
    };

    es.onerror = () => {
      setEntries((prev) => {
        const updated = [...prev];
        if (updated[0]?.isLoading) {
          updated[0] = {
            ...updated[0],
            error: "Connection to backend failed. Is the server running?",
            isLoading: false,
          };
        }
        return updated;
      });
      setIsLoading(false);
      es.close();
    };
  };

  return (
    <div className="min-h-screen flex flex-col max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="bg-blue-600 p-2 rounded-lg">
          <Database size={20} className="text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-100">SQLMind</h1>
          <p className="text-xs text-gray-500">Natural language to SQL agent</p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 text-xs text-green-400 bg-green-400/10 px-3 py-1.5 rounded-full">
          <Zap size={11} />
          <span>Chinook DB</span>
        </div>
      </div>

      {/* Input */}
      <div className="mb-8">
        <QueryInput onSubmit={handleSubmit} isLoading={isLoading} />
        <p className="text-xs text-gray-600 mt-2 ml-1">
          Try: "top 5 selling artists" · "how many tracks per genre" ·
          "customers from Brazil"
        </p>
      </div>

      {/* Results */}
      <div className="space-y-8 flex-1">
        {entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Database size={40} className="text-gray-700 mb-4" />
            <p className="text-gray-500 text-sm">
              Ask a question about your database
            </p>
            <p className="text-gray-600 text-xs mt-1">
              The agent will fetch the schema, write SQL, and explain the
              results
            </p>
          </div>
        )}

        {entries.map((entry, i) => (
          <div key={i} className="space-y-3">
            {/* Question */}
            <div className="flex items-start gap-3">
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
                Q
              </div>
              <p className="text-gray-100 text-sm pt-1">{entry.question}</p>
            </div>

            {/* Agent activity */}
            <div className="ml-10">
              <StreamStatus
                events={entry.events.filter((e) => e.type !== "complete")}
                isLoading={entry.isLoading}
              />
            </div>

            {/* Error */}
            {entry.error && (
              <div className="ml-10 bg-red-950/50 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
                {entry.error}
              </div>
            )}

            {/* Result */}
            {entry.result && (
              <div className="ml-10 space-y-3">
                {/* Explanation */}
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3">
                  <p className="text-gray-100 text-sm leading-relaxed">
                    {entry.result.explanation}
                  </p>
                  <div className="flex gap-4 mt-2 text-xs text-gray-500">
                    <span>{entry.result.tokens_used} tokens</span>
                    <span>
                      {(entry.result.execution_time_ms / 1000).toFixed(1)}s
                    </span>
                    {entry.result.retry_count > 0 && (
                      <span className="text-orange-400">
                        {entry.result.retry_count} retry
                      </span>
                    )}
                  </div>
                </div>

                {/* SQL */}
                <SqlDisplay sql={entry.result.sql} />

                {/* Table */}
                <ResultTable
                  rows={entry.result.rows}
                  rowCount={entry.result.row_count}
                />
              </div>
            )}

            {i < entries.length - 1 && <hr className="border-gray-800 mt-6" />}
          </div>
        ))}
      </div>
    </div>
  );
}
