"use client";
import {
  CheckCircle,
  Loader2,
  AlertCircle,
  Database,
  Code,
  Play,
  RefreshCw,
} from "lucide-react";

export interface StreamEvent {
  type: string;
  message?: string;
  table_count?: number;
  sql?: string;
  row_count?: number;
  attempt?: number;
  error?: string;
}

interface StreamStatusProps {
  events: StreamEvent[];
  isLoading: boolean;
}

function EventRow({ event }: { event: StreamEvent }) {
  if (event.type === "status") {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-xs">
        <Loader2 size={12} className="animate-spin text-blue-400" />
        <span>{event.message}</span>
      </div>
    );
  }
  if (event.type === "schema_fetched") {
    return (
      <div className="flex items-center gap-2 text-green-400 text-xs">
        <CheckCircle size={12} />
        <span>Schema fetched — {event.table_count} tables found</span>
      </div>
    );
  }
  if (event.type === "sql_generated") {
    return (
      <div className="flex items-center gap-2 text-blue-400 text-xs">
        <Code size={12} />
        <span>SQL generated</span>
      </div>
    );
  }
  if (event.type === "executing") {
    return (
      <div className="flex items-center gap-2 text-yellow-400 text-xs">
        <Play size={12} />
        <span>Query executed — {event.row_count} rows returned</span>
      </div>
    );
  }
  if (event.type === "retry") {
    return (
      <div className="flex items-center gap-2 text-orange-400 text-xs">
        <RefreshCw size={12} />
        <span>Query failed, retrying (attempt {event.attempt}/2)...</span>
      </div>
    );
  }
  if (event.type === "error") {
    return (
      <div className="flex items-center gap-2 text-red-400 text-xs">
        <AlertCircle size={12} />
        <span>{event.message || event.error}</span>
      </div>
    );
  }
  return null;
}

export default function StreamStatus({ events, isLoading }: StreamStatusProps) {
  if (events.length === 0 && !isLoading) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 space-y-1.5">
      <div className="flex items-center gap-2 text-gray-500 text-xs font-medium mb-2">
        <Database size={11} />
        <span>Agent activity</span>
      </div>
      {events.map((event, i) => (
        <EventRow key={i} event={event} />
      ))}
    </div>
  );
}
