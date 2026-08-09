# Security

This project is a consent-based browser observability and support platform. It deliberately excludes browser exploitation, arbitrary JavaScript execution, keylogging, credential capture, persistence, screen capture, webcam or microphone access, port scanning, and any hidden user action.

## Safe Diagnostic Boundary

Diagnostic actions are fixed server-side action types with strict parameter schemas. The client handles them with a switch statement and does not use `eval`, `Function`, dynamic imports, script injection, HTML injection, shell commands, or arbitrary URLs.

User-affecting support actions require a visible browser confirmation. Support-page navigation is limited to project-approved URLs.

## Operational Controls

Use a long random `JWT_SECRET`, terminate TLS before the app, configure trusted proxy addresses explicitly, and keep MySQL and Redis private. Do not trust client-submitted IP values. The server should use proxy headers only when the request came from a trusted proxy.

## Reporting Issues

Report security bugs privately to the project owner. Include reproduction steps, affected versions, expected behavior, and observed behavior.
