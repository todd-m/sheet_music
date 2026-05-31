# Sheet Music Library — Dev State

Auto-loaded by Claude Code at session start. `README.md` has the stable architecture overview; this file tracks live state, recent changes, and repo gotchas.

## Recent Changes

Most recent first; sourced from `git log`.

- **`make check-cdn`** *(uncommitted)* — Makefile target that grep-extracts the pinned PDF.js CDN URLs from `app/index.html` and HEAD-checks they're reachable; wired into `make ci`. Catches 404s on the pinned URLs (would have caught the v3 `.mjs` mistake); does not catch iOS-engine compatibility regressions.
- **Legacy iOS 15 PDF viewer fix** (7037acd) — PDF.js pinned to v3.11.174 legacy UMD and loaded via a classic `<script>` tag in `loadPdfJs()`, replacing the v4 ESM dynamic import that broke on older iPads (Safari 15). See gotcha below.
- **`make ci` / `make audit`** (2ff29ce) — Makefile targets for pip-audit vulnerability scanning.
- **Offline mode handling** (c1d565f, 2957ddd, 7584770, 64a4709) — merged feature: `createApp` models catalog status (`loading` / `ready` / `error`), search input is debounced, catalog-load failures surface a retry UI, PDF load errors show clearer messages. Design spec lives in `docs/`.
- **Starlette security patch** (94a4142).
- **404 handling + tests** (47a55a5) — server now responds correctly to missing routes / Drive files; coverage added.
- **Auxiliary Drive endpoint** (e13eb7e) — additional endpoint exercising the configured service user.
- **`Copy ingest command` button** (9a480ed) — viewer panel for unconfigured volumes offers one-click copy of the `add-volume` CLI invocation.
- **Script declare-order fix for WebKit** (4781dff) — search results were silently failing on Safari due to script ordering. See gotcha below.
- **Service-account Drive auth** (98b25a1) — server uses `credentials.json` Bearer auth when present, falls back to public links otherwise.
- **Extracted `app/lib.js`** (a32a679) — testable JS (search, `escapeHtml`, rendering, fullscreen, tiles, viewer chrome) extracted from `index.html`. PDF/canvas code stays inline because it depends on pdf.js.

## Planned / In-Progress

Nothing actively tracked in the repo.

## Conventions and Gotchas

- **PDF.js is pinned to v3.11.174 legacy UMD for iOS 15 / Safari 15 support.** v4+ raised the minimum Safari version to 16.4 and breaks older iPads. The v3 legacy build ships UMD only — it is loaded via a classic `<script>` tag in `loadPdfJs()` (`app/index.html`), **not** via ES-module `import()`. Do not upgrade these URLs without re-testing on an iOS 15 device. The reasoning is also pinned in a comment at the URL constants.
- **WebKit-sensitive `<script>` order in `app/index.html`** — search results silently failed on Safari before commit 4781dff because of script declare order. When adding scripts, verify Safari/WebKit behaviour, not just Chrome/Firefox.
- **PDF parser uses character position data**, not whitespace splitting (`ingestion/parsers/pdf_parser.py`). Multi-word titles like "All Of Me" depend on this. Don't refactor to naive `.split()`.
- **Two Drive auth modes**: service account via `credentials.json` (preferred for private files) or public links + `resourceKey` (fallback). The server auto-detects which at startup. `credentials.json` is gitignored.
- **Tests**: `make test` runs Python (pytest) and JS (`node --test`) together. JS tests need `npm install` first to pull jsdom.
- **`catalog.json` is hand-editable** — page-offset formula is `actual_pdf_page = nominalPage + pageOffset`.
