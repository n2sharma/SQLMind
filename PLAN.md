# SQLMind V1.0 — Natural Language to SQL Agent
### Architecture & Build Plan
> Goal: Working demo in one day. Every decision has a "why".

---

## 1. Problem Statement

Most data lives in PostgreSQL. Most people can't write SQL. SQLMind sits between the two:
a user types a question in plain English, an AI agent reads the schema, writes SQL, validates
it for safety, executes it, and explains the result — live, streamed to the browser.
V1.0 is the minimal version that proves the concept end-to-end.

---

## 2. V1.0 Functional Requirements

### What We Are Building (today)

| # | Feature | Notes |
|---|---------|-------|
| F1 | Schema discovery | Introspect any local PostgreSQL DB: tables, columns, types, PKs, FKs |
| F2 | Natural language input | Plain English question via chat UI or REST API |
| F3 | SQL generation | Gemini 1.5 Flash generates SQL from question + schema |
| F4 | SQL validation | Block DDL (DROP/CREATE/ALTER), block DML without WHERE, auto-add LIMIT |
| F5 | Safe execution | SELECT only; LIMIT 100 enforced |
| F6 | Self-correction retry | If DB error → agent sends error back to LLM → gets fixed SQL (max 2 retries) |
| F7 | Plain English explanation | LLM converts rows to a readable answer |
| F8 | SSE streaming | Browser sees live progress: schema fetched → SQL → executing → result |
| F9 | Query history | Save every query + result to a single PostgreSQL table |
| F10 | Chat UI | Next.js single-page app: input + live status + SQL display + result table |

### What We Are NOT Building (V2.0+)

Auth, multi-DB per session, query caching, CSV export, performance hints,
query suggestions, feedback thumbs-up/down, complex session management.

---

## 3. Tech Stack Decisions

### Backend

| Layer | Choice | Why This | Why Not X |
|-------|--------|----------|-----------|
| Language | **Python 3.11+** | Fastest path to AI tooling; asyncio native; better library support for SQL parsing (sqlglot) | Node.js: fine, but Python ecosystem wins for AI/data tools |
| Framework | **FastAPI** | Async out of the box; SSE via `StreamingResponse`; auto-generates OpenAPI docs; minimal boilerplate | Flask: sync by default; Django: way too heavy |
| LLM SDK | **google-genai** (new SDK) | Gemini 1.5 Flash is free (15 RPM, 1M tokens/day); full function-calling support | `google-generativeai`: deprecated; Anthropic: paid only; OpenAI: paid (but supported as fallback — see below) |
| DB driver | **asyncpg** | Async PostgreSQL driver; fast; works natively with FastAPI's async handlers | psycopg2: sync only; SQLAlchemy: too much ORM for this use case |
| SQL parser | **sqlglot** | Pure Python; excellent PostgreSQL dialect; parses SQL to AST for safe DDL/DML detection | regex: unreliable; pg native parser: requires a live DB connection |
| Logging | **structlog** | Structured JSON logs; binds context (session_id, retry_count) cleanly | Python logging: unstructured; print(): not production-grade |

### Frontend

| Layer | Choice | Why |
|-------|--------|-----|
| Framework | **Next.js 14 (TypeScript)** | Naman's stack; SSE via native EventSource; React for live updates |
| Styling | **Tailwind CSS** | Fastest way to build a clean UI without fighting CSS |
| API consumption | **EventSource API** | Native browser SSE client; no library needed |

### How to Switch from Gemini (free) to OpenAI (paid)

Gemini is the default. You never need to touch code to switch.

**Step 1:** Get an OpenAI API key from platform.openai.com → Billing → API Keys

**Step 2:** In your `.env`, change:
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
# Recommended model: gpt-4o-mini (cheap + fast) or gpt-4o (best quality)
OPENAI_MODEL=gpt-4o-mini
```

**Step 3:** Restart the backend. Done.

The agent factory reads `MODEL_PROVIDER` at startup and instantiates the right client.
Function calling (tool use) works identically in both SDKs — the tool definitions you write
once work for both providers.

---

## 4. V1.0 Architecture (HLD)

```
┌─────────────────────────────────────────────────────────────┐
│              Browser (Next.js Chat UI)                       │
│   EventSource → GET /api/query/stream                        │
└───────────────────────────┬─────────────────────────────────┘
                            │ SSE stream
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│  POST /api/query | GET /api/query/stream | GET /api/schema  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLMind Agent                              │
│  State machine: SCHEMA → GENERATE → VALIDATE → EXECUTE       │
│                → EXPLAIN → DONE  (RETRY on error, max 2)    │
└──────┬────────────────────────────┬──────────────────────────┘
       │ tool calls                 │ LLM calls
       ▼                            ▼
┌────────────────┐        ┌──────────────────────┐
│   Tool Layer   │        │  Gemini 1.5 Flash     │
│  get_schema    │        │  (or OpenAI GPT-4o-m) │
│  validate_q    │        │  Function calling API │
│  run_query     │        └──────────────────────┘
│  explain_r     │
│  fix_query     │
└──────┬─────────┘
       │
       ▼
┌──────────────────────────────────────┐
│         PostgreSQL (local)           │
│  User DB: the DB being queried       │
│  Meta DB: query_history table only   │
└──────────────────────────────────────┘
```

**Data flow in plain English:**
1. User asks: *"How many orders were placed last month?"*
2. FastAPI receives request → spawns agent
3. Agent calls `get_schema` → reads PostgreSQL information_schema
4. Agent sends schema + question + tool definitions to Gemini
5. Gemini calls `run_query` with SQL it generated → agent validates first
6. If DB error → agent calls `fix_query` → Gemini corrects SQL → retry
7. Agent calls `explain_result` → Gemini writes a plain English answer
8. Every step emits an SSE event → browser shows live progress

---

## 5. Agent Loop (LLD)

### State Machine

```
START ──► SCHEMA_FETCH
               │ schema received
               ▼
          SQL_GENERATE ──────────────────────────────────┐
               │ LLM returns tool call: run_query         │
               ▼                                          │
           VALIDATE                                       │
               │                                          │
        ┌──────┴──────────┐                               │
     invalid            valid                             │
        │                 │                               │
        ▼                 ▼                               │
      ERROR           EXECUTE                             │
                          │                               │
               ┌──────────┴──────────┐                   │
            db error             success                  │
               │                    │                     │
               ▼                    ▼                     │
            RETRY               EXPLAIN                   │
          (max 2x)                  │                     │
               │ new SQL            ▼                     │
               └────────────►    DONE                     │
                        (back to VALIDATE)                │
                                                          │
          MAX ITERATIONS GUARD: 8 total steps ────────────┘
          If exceeded: return error "Query too complex"
```

**Why a max iteration guard?**
LLMs can get stuck in tool-calling loops. 8 steps is enough for the happy path
(5 steps) plus 2 retries. Anything beyond that is a sign the model is confused.

### Retry Logic
- Retry only on database execution errors (column doesn't exist, syntax error from pg)
- Never retry on validation failures (those are safety blocks, not recoverable by LLM)
- On retry: send original question + failed SQL + error message to `fix_query`
- Max 2 retries (3 total attempts)

---

## 6. Tool Definitions

### `get_schema`
Fetches the full schema of the user's PostgreSQL database.
- **Input:** `{ tables?: string[] }` — optional filter; if omitted, fetches all tables
- **Output:** `{ tables: [{ name, columns: [{name, type, nullable, is_pk, is_fk, references}] }] }`
- **Error:** Raises with "Cannot connect to database: {pg error}" — agent stops immediately

### `validate_query`
Parses SQL with sqlglot and checks for safety violations before any execution.
- **Input:** `{ sql: string }`
- **Output:** `{ valid: bool, is_safe: bool, issues: [str], sql_with_limit: str }`
- **Safety rules:** Block DDL (DROP/CREATE/ALTER/TRUNCATE), block DML without WHERE, auto-add `LIMIT 100`
- **Error:** If sqlglot parse fails → `{ valid: false, issues: ["Parse error: ..."] }`

### `run_query`
Executes the validated SQL against the user's database. SELECT only.
- **Input:** `{ sql: string }`
- **Output:** `{ rows: list[dict], row_count: int, execution_time_ms: int }`
- **Error:** Raises with the raw PostgreSQL error message — agent uses this for `fix_query`

### `explain_result`
Calls the LLM to convert SQL rows into a plain English answer.
- **Input:** `{ question: str, sql: str, rows: list[dict], row_count: int }`
- **Output:** `{ explanation: str }`
- **Error:** Falls back to `"Query returned {row_count} rows."` if LLM call fails

### `fix_query`
Given a failing SQL and its error, asks the LLM to generate a corrected version.
- **Input:** `{ original_question: str, failed_sql: str, error_message: str, schema: str }`
- **Output:** `{ fixed_sql: str, explanation: str }`
- **Error:** Returns `{ fixed_sql: "", explanation: "Could not fix" }` → triggers final error state

---

## 7. API Design (V1.0)

```
GET  /health
  Response: { "status": "ok", "db": "connected", "timestamp": "..." }

GET  /api/schema
  Response: { "tables": [...] }
  Use: debug helper to preview the schema the agent sees (reads USER_DB_URL from env)

POST /api/query
  Body:     { "question": str }
  Response: { "sql": str, "rows": [...], "row_count": int, "explanation": str,
              "tokens_used": int, "execution_time_ms": int, "retry_count": int }
  Errors:   400 (missing question), 422 (unsafe SQL blocked), 500 (failed after retries)
  Note: DB connection is always USER_DB_URL from .env — no dynamic DB URLs accepted

GET  /api/query/stream?question=...
  Content-Type: text/event-stream
  Events (SSE):
    data: {"type": "schema_fetched", "table_count": 5}
    data: {"type": "sql_generated", "sql": "SELECT ..."}
    data: {"type": "validation_passed"}
    data: {"type": "executing"}
    data: {"type": "retry", "attempt": 1, "error": "column x does not exist"}
    data: {"type": "complete", "rows": [...], "explanation": "...", "tokens_used": 840}
    data: {"type": "error", "message": "..."}
```

**Why SSE over WebSockets?**
SSE is one-directional (server → client), which is all we need. It works over plain HTTP,
needs no handshake upgrade, and EventSource in the browser auto-reconnects. WebSockets add
complexity (bidirectional, connection management) for no benefit here.

---

## 8. Database Schema (V1.0)

One table. That's it.

```sql
CREATE TABLE IF NOT EXISTS query_history (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question         TEXT NOT NULL,
  generated_sql    TEXT,
  rows_returned    INTEGER,
  execution_time_ms INTEGER,
  tokens_used      INTEGER,
  status           TEXT CHECK (status IN ('success', 'error', 'retry_success')),
  error_message    TEXT,
  retry_count      INTEGER DEFAULT 0,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

**Why no sessions table?**
V1.0 doesn't have user accounts or session state. A UUID in the URL is enough to
group queries if we need it later. Adding a sessions table now is premature.

---

## 9. Project Structure

```
SQLMind/
├── PLAN.md
├── README.md                       ← 5-command quick start
├── .env.example
├── .env                            ← gitignored
├── .gitignore
│
├── backend/
│   ├── main.py                     ← FastAPI app: routes, startup, CORS
│   ├── config.py                   ← Load + validate all env vars (pydantic Settings)
│   ├── requirements.txt
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         ← The agent loop: state machine + tool dispatch
│   │   ├── llm_client.py           ← Factory: returns Gemini or OpenAI client based on MODEL_PROVIDER
│   │   └── tools/
│   │       ├── __init__.py         ← Tool registry: list of all tool definitions
│   │       ├── get_schema.py
│   │       ├── validate_query.py
│   │       ├── run_query.py
│   │       ├── explain_result.py
│   │       └── fix_query.py
│   │
│   ├── db/
│   │   ├── client.py               ← asyncpg pool for meta DB
│   │   ├── migrations.py           ← CREATE TABLE IF NOT EXISTS on startup
│   │   └── history.py              ← save_query(), get_history()
│   │
│   └── utils/
│       ├── logger.py               ← structlog JSON logger setup
│       └── sql_safety.py           ← sqlglot-based DDL/DML detection helpers
│
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── tailwind.config.ts
    └── src/
        ├── app/
        │   ├── page.tsx            ← Single page: full chat UI
        │   └── layout.tsx
        └── components/
            ├── QueryInput.tsx      ← Text input + submit button
            ├── StreamStatus.tsx    ← Live SSE event display (schema fetched / generating SQL...)
            ├── SqlDisplay.tsx      ← Syntax-highlighted SQL block
            └── ResultTable.tsx     ← Paginated data table
```

**`requirements.txt` contents:**
```
fastapi
uvicorn[standard]
asyncpg
sqlglot
structlog
pydantic-settings
google-genai
openai
python-dotenv
```

**Why separate backend/ and frontend/?**
Two different runtimes (Python and Node.js), two different `package.json`/`requirements.txt`.
Keeping them in sibling folders makes it obvious what starts where.

**Why `llm_client.py` as a factory?**
All the Gemini vs OpenAI switching logic lives in one file. Every other file just calls
`get_llm_client()` and doesn't care which provider is active.

---

## 10. One-Day Build Plan

### Block 1 — Backend Scaffold (1.5h)
**Build:** FastAPI app boots, connects to PostgreSQL meta DB, `query_history` table created
on startup, `/health` returns 200, structlog outputs JSON.

**Learn:** Why Pydantic Settings beats `os.getenv()` everywhere (type safety, validation at startup, not at runtime).

**Verify:**
```bash
cd backend && uvicorn main:app --reload
curl http://localhost:8000/health
# → {"status":"ok","db":"connected"}
```

**Commit:** `feat: bootstrap FastAPI backend with PostgreSQL, structlog, and health endpoint`

---

### Block 2 — All 5 Tools (1.5h)
**Build:** Implement each tool file. Test each manually with a Python REPL or quick test script.
Focus: get_schema reads real schema, validate_query blocks DDL, run_query executes SELECT.

**Learn:** How sqlglot parses SQL to an AST — why AST-based safety checks beat regex
(regex can't handle `/*drop*/SELECT` or aliased DDL).

**Verify:**
```bash
cd backend && python -c "
import asyncio
from agent.tools.get_schema import get_schema
print(asyncio.run(get_schema({})))
"
```

**Commit:** `feat: implement all 5 agent tools with sqlglot validation and asyncpg execution`

---

### Block 3 — Agent Loop + POST /api/query (1.5h)
**Build:** `orchestrator.py` — the state machine loop. Wire all tools. Handle retries.
Expose `POST /api/query` (sync, returns full result when done).

**Learn:** How LLM function calling works in a loop: send tools → get `function_call` response
→ execute tool → send `function_response` → repeat until LLM stops calling tools.
This is the core pattern of every AI agent.

**Verify:**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "how many tables are in the database?"}'
# → {sql, rows, explanation, tokens_used, ...}
```

**Commit:** `feat: implement SQLMind agent loop with tool orchestration and retry logic`

---

### Block 4 — SSE Streaming (1h)
**Build:** `GET /api/query/stream` — same agent, but each state transition emits an SSE event.
Use FastAPI's `StreamingResponse` with an async generator.

**Learn:** How `StreamingResponse` + async generator works in FastAPI. Why the agent must
`yield` events rather than return them all at once. How `EventSource` in the browser
auto-parses `data: {...}\n\n` format.

**Verify:**
```bash
curl -N "http://localhost:8000/api/query/stream?question=how+many+tables"
# → Live SSE events printed to terminal
```

**Commit:** `feat: add SSE streaming endpoint with live agent progress events`

---

### Block 5 — Frontend Chat UI (1.5h)
**Build:** Next.js single-page app. `QueryInput` sends question. `EventSource` opens SSE
stream. `StreamStatus` shows live events. `SqlDisplay` shows generated SQL. `ResultTable`
shows rows. `explain_result` explanation shown at the end.

**Learn:** How EventSource works in React — why you open it in a `useEffect`, why you close it
in the cleanup function. The pattern for streaming AI UIs (show partial state, not just a spinner).

**Verify:** Open browser at `http://localhost:3000`, type a question, watch it stream live.

**Commit:** `feat: add Next.js chat UI with SSE streaming, SQL display, and result table`

---

### Block 6 — Polish & README (0.5h)
**Build:** `README.md` with 5-command quick start. `.env.example` with all vars. Final
`.gitignore`. Smoke test the full flow end-to-end.

**Commit:** `docs: add README, env example, and final V1.0 cleanup`

---

## 11. Getting Started

### Prerequisites
```bash
python --version      # need 3.11+
node --version        # need 20+
psql --version        # need PostgreSQL 15+
```

### Get a Free Gemini API Key (3 steps)
1. Go to aistudio.google.com
2. Click "Get API Key" → Create API key in new project
3. Copy the key → paste into `.env` as `GEMINI_API_KEY=...`

Free tier: 15 requests/minute, 1 million tokens/day. Enough for development.

### PostgreSQL Setup
```bash
createdb sqlmind_meta    # meta DB (query history)
createdb chinook         # sample DB to query (or use any existing local DB)
# Load Chinook sample data: https://github.com/leomaurodesenv/game-company-sql
```

### Environment Variables
Create `.env` in project root:
```bash
# LLM Provider: "gemini" (free) or "openai" (paid)
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your-key-here

# Only needed if MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Meta DB (query history storage)
DATABASE_URL=postgresql://localhost:5432/sqlmind_meta

# The DB users will query (hardcoded in backend — not exposed as API param)
USER_DB_URL=postgresql://localhost:5432/chinook

# Server
PORT=8000
LOG_LEVEL=debug

# Agent limits
AGENT_MAX_ITERATIONS=8
AGENT_MAX_RETRIES=2
AGENT_TIMEOUT_SECONDS=30
```

### Install & Run
```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
# → open http://localhost:3000
```

---

## 12. Upgrade Path (V1.0 → V2.0)

| Feature | V1.0 | V2.0 |
|---------|------|------|
| Auth | None (open API) | JWT or Clerk |
| Sessions | Implicit (UUID per request) | Explicit session management |
| Multi-DB | Single USER_DB_URL | User connects any DB per session |
| Query caching | None | Redis cache on (question hash → result) |
| Feedback | None | Thumbs up/down saved to DB |
| CSV export | None | Download button on result table |
| Performance hints | None | EXPLAIN ANALYZE + index suggestions |
| Deployment | Local only | Docker Compose → Railway/Render |

---

*Every decision above has a "why". Every block has a test. Read this once before writing
a single line of code. Come back when you're lost.*
