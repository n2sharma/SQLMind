# SQLMind — Natural Language to SQL Agent

Ask questions about your PostgreSQL database in plain English.
The AI agent fetches the schema, writes SQL, validates it, executes it, and explains the result — live, streamed to the browser.

## Quick Start

**1. Clone and setup**

```bash
git clone <your-repo>
cd SQLMind
cp .env.example .env
# Edit .env with your API key and DB URLs
```

**2. Start backend**

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload --port 8000
```

**3. Start frontend**

```bash
cd frontend
npm install && npm run dev
```

**4. Open browser**
http://localhost:3000

## Stack

- **Backend:** Python + FastAPI + asyncpg
- **Agent:** Custom tool-calling loop (no LangChain)
- **LLM:** OpenAI GPT-4o-mini (or Gemini 2.0 Flash — set `MODEL_PROVIDER=gemini`)
- **DB:** PostgreSQL (sample: Chinook music store)
- **Frontend:** Next.js + TypeScript + Tailwind

## Switch LLM Provider

```bash
# Use Gemini (free)
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your-key

# Use OpenAI (paid, better quality)
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
```
