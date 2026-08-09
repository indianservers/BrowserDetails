# Browser Monitor

Browser Monitor is a consent-based browser diagnostics and support platform. It provides a Python/FastAPI server with MySQL, WebSockets, a live administrator dashboard, and a small TypeScript client SDK.

It is intentionally not an exploitation framework. There is no arbitrary JavaScript execution, credential capture, keylogging, persistence, screen capture, webcam/microphone access, browser attack module, or internal-network scanning.

## Structure

```text
browser-monitor/
  server/   FastAPI, SQLAlchemy 2, Alembic, dashboard, WebSockets
  client/   TypeScript SDK and demo page
  nginx/    Reverse proxy config
```

## Quick Start

1. Copy `.env.example` to `.env` and replace `JWT_SECRET`.
2. Start services:

```bash
docker compose up --build
```

3. Run migrations from the server container:

```bash
docker compose exec server alembic upgrade head
```

4. Create the first administrator:

```bash
docker compose exec server python -m app.workers.create_admin admin@example.com "replace-me"
```

5. Create a project row and allowed origin in MySQL, then install the SDK on an approved page:

```html
<script
  src="https://monitor.example.com/sdk/client-monitor.min.js"
  data-project-id="PUBLIC_PROJECT_ID"
  data-consent-mode="explicit"
  defer></script>
```

The dashboard is served at `http://localhost:8000/` in development.

## Current Implementation

This scaffold includes the Phase 1 foundation plus a safe diagnostic-action skeleton:

- Client registration with allowed-origin validation.
- Argon2-backed administrator login and secure server-side dashboard sessions.
- Consent-required registration and withdrawal handling.
- Heartbeats and WebSocket presence.
- Browser, display, graphics, network, and page diagnostics limited to page-safe APIs.
- Client-side bounded event queue, route redaction, sanitized error monitoring, performance snapshots, consent lifecycle events, and user-visible support action confirmations.
- BeEF-style collapsible client grouping in the dashboard without offensive features.
- Fixed diagnostic action allowlist and JSON-schema validation.
- Project-approved support URL enforcement.
- Privacy helpers for IP truncation/hashing and sensitive payload redaction.
- Docker Compose for FastAPI, MySQL 8, Redis, worker, and Nginx.

## Development

Server:

```bash
cd server
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Client:

```bash
cd client
npm install
npm run build
npm test
```

## Production Notes

Use HTTPS, secure cookies, strict CORS, a locked-down proxy trust configuration, private MySQL/Redis networking, regular backups, log rotation, and retention jobs. Redis is intended for scalable live presence and pub/sub; MySQL can act as a small-deployment fallback with lower real-time scalability.
