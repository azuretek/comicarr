# Comicarr Frontend

The frontend is a React 19 + Vite application. Production builds are served by
the FastAPI application from `frontend/dist`.

## Common Commands

```bash
npm run dev        # https://comicarr.localhost:1355 (portless — preferred)
npm run dev:vite   # raw Vite on localhost:5173 (escape hatch)
npm run lint
npm run format:check
npm run typecheck
npm run test:run
npm run build
```

`npm run dev` uses [portless](https://github.com/vercel-labs/portless) so the
frontend keeps a stable name (`https://comicarr.localhost:1355`) instead of
competing for port 5173 with other local projects. The proxy listens on
unprivileged port **1355** (no sudo). First HTTPS session may need
`npx portless trust`. Use `dev:vite` only when something needs a bare host:port.

## Backend during dev

When using the Vite dev server with a separately running backend, Comicarr
defaults to port 8090. The Vite proxy targets `http://localhost:8090`
(override with `VITE_API_PROXY_TARGET` if needed). API traffic still goes
through the Vite origin, so the browser only talks to `comicarr.localhost`.

## E2E Tests

The Playwright suite runs against the built React bundle served by Comicarr,
not against Vite or MSW. Build the frontend first, then run the suite from this
directory:

```bash
npm run build
npm run test:e2e:smoke
npm run test:e2e:full
```

`npm run test:e2e` is an alias for the required Chromium smoke suite. Smoke
tests start Comicarr with an isolated seeded data directory, sign in through
the real login page, and verify protected navigation plus API/auth contracts.
The full suite starts with an empty data directory and covers the first-run
setup token flow plus restart behavior.

Useful environment variables:

- `COMICARR_E2E_PORT`: port for the seeded smoke server, default `18090`.
- `COMICARR_E2E_BASE_URL`: use an already-running Comicarr instance instead
  of letting Playwright start one.
- `COMICARR_E2E_DATADIR`: data directory for the managed smoke server.
- `COMICARR_E2E_PYTHON`: Python executable used to start `Comicarr.py`.
- `COMICARR_E2E_KEEP_DATA`: set to `1` to preserve generated data for
  debugging.
- `COMICARR_E2E_FULL_PORT`: alternate port for the first-run full suite,
  default `COMICARR_E2E_PORT + 1`.
- `COMICARR_E2E_FULL_DATADIR`: data directory for the first-run full suite.

When debugging failures, inspect `playwright-report/` and `test-results/e2e/`.
Both directories are ignored locally and uploaded by CI on failure.
