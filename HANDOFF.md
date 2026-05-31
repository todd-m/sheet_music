# HANDOFF

**Session focus:** iOS 15 legacy iPad PDF viewer fix + CDN liveness guard.

**Hard constraints to preserve across sessions:**

1. **PDF.js v3 pin must stay.** Do not upgrade `PDFJS_URL` / `PDFJS_WORKER_URL` without re-testing on an iOS 15 device. PDF.js v4+ raised the minimum to Safari 16.4 / iOS 16.4 and breaks supported old iPads. Pin reasoning lives in the comment block at `app/index.html:285-291`.
2. **`make check-cdn` catches 404s only, not engine-compat regressions.** A green CI does NOT mean iOS 15 still works. iOS 15 regressions can only be caught on a real iOS 15 device (or BrowserStack/Sauce with a Safari 15 target, which the project does not use).
3. **iOS 15.8.8 iPad is a supported target device** for this app. Future feature work should respect that constraint — prefer transpiled / UMD libraries over modern ESM that needs Safari 16+ APIs.

## Just completed

- `7037acd` — PDF.js pinned to **v3.11.174 legacy UMD**, loaded via classic `<script>` tag in `loadPdfJs()` (`app/index.html:286-318`). Replaces the v4 ESM dynamic import that silently failed on iOS 15 Safari 15.
- `bcc7e6c` — `CLAUDE.md` created with recent-changes log and the PDF.js pin documented as a gotcha.

**Path taken** (skip these dead ends if re-investigating):
v4 modern (`cdnjs .../pdf.min.mjs`) → v4 legacy (jsdelivr `.../legacy/build/pdf.min.mjs`) → v3 `.mjs` (404 — v3 has no ESM build) → **v3 UMD via `<script>` tag**.

**Diagnostic detour:** No remote debugger access was available on the iPad (Safari Develop menu attach didn't work), so `showViewerError` was temporarily restyled with `white-space: pre-wrap` + monospace to surface multi-line diagnostics directly on the iPad screen. Reverted once the fix was confirmed.

## In progress

Nothing in flight. `git status` shows `M Makefile` — that's the `check-cdn` target ready to commit (see Next up), not partial work.

## Next up

- **Commit the `check-cdn` Make target** (`Makefile:32-36`) plus the `.PHONY` and `ci` updates (`Makefile:6, 38`). Verified working: `make check-cdn` does `HEAD` requests against the pinned PDF.js URLs grep-extracted from `app/index.html` and exits non-zero on any non-200.

## Open questions / decisions pending

None.

Decisions already settled this session (do not re-litigate):
- Unit-testing `loadPdfJs()` was considered and rejected: jsdom/Node V8 cannot reproduce engine-specific Safari 15 module-eval failures, so a green jsdom test would hide the bug rather than catch it. Real-device verification is the only meaningful test.
- Extracting `loadPdfJs` from `app/index.html` into `app/lib.js` for testability was discussed but not pursued; it's a refactor, not a fix, and conflicts with the existing convention that pdf.js-dependent code stays inline (per commit `a32a679`).
