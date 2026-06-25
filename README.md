# Meeting Agent

Meeting Agent is an AI meeting assistant built around a Python backend and a Next.js frontend.
The active mainline is `FastAPI + Next.js`.

## Current Architecture

- `api/`: FastAPI HTTP entry, routers, schemas, in-process job manager
- `web/`: Next.js App Router frontend, Playwright E2E tests
- `services/`: meeting processing pipeline orchestration
- `agents/`: chat agent and multi-turn Q&A
- `chains/`: minutes extraction and export chains
- `db/`: SQLAlchemy models and repository layer
- `rag/`: embeddings, retrieval, reranking, chunking
- `engines/`: ASR, audio, PDF and LLM-related engines
- `storage/`: local runtime storage for uploaded files, templates and outputs

## Tech Stack

Backend:

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL + pgvector
- Ollama
- LangGraph / LangChain Core
- Faster-Whisper / FunASR

Frontend:

- Next.js
- React
- TypeScript
- Tailwind CSS
- Playwright

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL
- Ollama
- `ffmpeg` and `ffprobe`

## Backend Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Configure environment variables in `.env`. The key variables are:

- `DATABASE_URL`
- `OLLAMA_BASE_URL`
- `LLM_MODEL`
- `WHISPER_MODEL`

Start the API from the repository root:

```powershell
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing
```

## Frontend Setup

Install frontend dependencies:

```powershell
cd web
npm install
```

Run a production-style frontend session:

```powershell
cd web
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Frontend URL:

- `http://127.0.0.1:3000`

API URL:

- `http://127.0.0.1:8000/api`

If needed, override the frontend API target with:

- `NEXT_PUBLIC_API_BASE_URL`

## Mainline Features

Current primary user flows:

- `/login` and `/register`: local account registration and login with JWT-based API auth
- `/meetings/new`: upload local audio or video files and generate meeting minutes
- `/realtime`: record from the browser microphone, stream chunked transcription to the backend, optionally run speaker diarization, then generate a meeting
- `/meetings/[id]`: inspect minutes, structured todos, resolutions, transcript, meeting chat, and HTML summary preview/download
- `/todos`: view and maintain structured action items across meetings
- `/chat`: single-meeting and cross-meeting Q&A
- `/stats`: overview metrics and charts

HTML summary support:

- The meeting detail page can generate a visual HTML summary from stored minutes, action items, resolutions, and transcript context.
- Generated HTML summaries are stored under `storage/output/` and can be previewed or downloaded from the detail page.

Realtime recording support:

- Browser audio is recorded in chunks on the frontend and uploaded to the backend session API.
- The backend converts chunks to WAV, runs ASR incrementally, keeps an in-memory realtime session, and can finalize that session into a normal stored meeting.
- After recording stops, the user can optionally run offline speaker diarization before generating the final meeting.

## Mainline API Additions

Auth routes:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Meeting-related routes:

- `GET /api/meetings/{id}`
- `GET /api/meetings/{id}/transcript`
- `POST /api/meetings/{id}/html-summary/generate`
- `GET /api/meetings/{id}/html-summary`

Todo routes:

- `GET /api/todos`
- `POST /api/meetings/{id}/todos`
- `PATCH /api/todos/{todo_id}`
- `POST /api/todos/{todo_id}/status`
- `GET /api/todos/{todo_id}/logs`

Realtime session routes:

- `POST /api/realtime/sessions`
- `GET /api/realtime/sessions/{session_id}`
- `POST /api/realtime/sessions/{session_id}/chunks`
- `POST /api/realtime/sessions/{session_id}/stop`
- `POST /api/realtime/sessions/{session_id}/diarize`
- `POST /api/realtime/sessions/{session_id}/generate`
- `DELETE /api/realtime/sessions/{session_id}`

## E2E Validation

Default E2E auth behavior:

- the Playwright helpers log in through `/api/auth/login`
- by default they use the migrated admin account: `admin / ChangeMe123!`
- this default assumes the database already contains sample meetings owned by that admin account
- override with `PLAYWRIGHT_E2E_USERNAME`, `PLAYWRIGHT_E2E_PASSWORD`, `PLAYWRIGHT_E2E_EMAIL`, and `PLAYWRIGHT_E2E_USE_ADMIN=false` if you want a dedicated test user

Migration compatibility note:

- the Alembic chain now includes compatibility revisions for the old mainline, including the legacy `86cee12a749a` step
- `alembic upgrade head` should advance old databases to `20260625_0002`

Run smoke tests:

```powershell
cd web
npm run test:e2e:smoke
```

Run the full E2E suite:

```powershell
cd web
npm run test:e2e:full
```

## Recommended Start Order

1. Start the FastAPI backend.
2. Run `alembic upgrade head`.
2. Build and start the Next.js frontend.
3. Run `npm run test:e2e:smoke`.
4. Run `npm run test:e2e:full` before release or deployment.

## Notes

- `main.py` is still available as a local CLI entry for utility workflows.
- Historical cutover notes are archived under `docs/archive/streamlit-cutover/`.
