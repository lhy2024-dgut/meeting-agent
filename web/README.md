# Meeting Agent Frontend

This is the active Next.js frontend for Meeting Agent.

## Location

- Frontend: `C:\Users\Administrator\Desktop\meeting-agent\web`
- Backend: `C:\Users\Administrator\Desktop\meeting-agent\api`

## Start the Backend

From the repository root:

```powershell
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

## Start the Frontend

From `web/`:

```powershell
npm install
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

## URLs

- Frontend: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000/api`

The frontend defaults to `http://127.0.0.1:8000/api`.
Override it with `NEXT_PUBLIC_API_BASE_URL` if needed.

## E2E

Run smoke tests:

```powershell
npm run test:e2e:smoke
```

Run the full suite:

```powershell
npm run test:e2e:full
```

## Covered Flows

- home dashboard
- meeting history search, filters, pagination, delete, project edit
- upload page and template preview
- meeting detail export and regenerate
- single-meeting chat
- cross-meeting source jump
- stats page
