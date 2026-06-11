# Sheet Music Library — Dev State

Auto-loaded by Claude Code at session start. `README.md` has the stable architecture overview; this file tracks live state, recent changes, and repo gotchas.

## Recent Changes

Most recent first; sourced from `git log`.

- **App auth token** *(uncommitted)* — `/api/pdf/{id}` and `/drive/file` now require a shared secret (`Authorization: Bearer` or `?token=`), sourced from `SHEET_MUSIC_TOKEN` env var or gitignored `token.txt`; fails closed (503) if unconfigured. `/api/catalog` and the SPA stay open (titles only). The SPA prompts once for the token (stored in localStorage, helpers in `lib.js`); on 401 it clears and re-prompts once. `require_token` is duplicated in `routers/drive_file.py` on purpose (self-containment for future extraction). Closes the `TODO: add auth`. Gotcha: that router imports Google's `Request` as `GoogleAuthRequest` — bare `Request` is FastAPI's.

- **Standards alignment pass** *(uncommitted)* — adopted `~/Projects/standards/STANDARDS.md`: venv renamed `env` → `.venv`, deps repinned with `~=` in `requirements.txt` (+ `ruff`, `pytest-cov`), ruff lint/format applied repo-wide (config in `pyproject.toml`), pytest coverage gate `--cov-fail-under=80` (currently 86%), JS tests migrated `node --test` → Vitest, `make lint` wired into `make ci`, GitHub Actions workflow added (`.github/workflows/ci.yml`).
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
- **Tests**: `make test` runs Python (pytest, with an 80% coverage gate from `pyproject.toml`) and JS (Vitest) together. JS tests need `npm ci` first (jsdom + vitest). The JS suite runs in Vitest's `node` environment because it builds its own JSDOM and loads `app/lib.js` via a data-URL import — which is also why there's no JS coverage gate (istanbul can't instrument data-URL modules).
- **Lint**: `make lint` = `ruff check` + `ruff format --check`; config lives in `pyproject.toml` (line-length 100). Part of `make ci`.
- **Venv is `.venv`** (per `~/Projects/standards/STANDARDS.md`); a stale `env/` dir may exist locally until removed.
- **`catalog.json` is hand-editable** — page-offset formula is `actual_pdf_page = nominalPage + pageOffset`.
