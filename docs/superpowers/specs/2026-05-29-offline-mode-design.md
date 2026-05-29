# Offline Mode Handling

**Date:** 2026-05-29

## Problem

When the local server is unreachable or returns an error, `loadCatalog()` silently swallows the failure and leaves the catalog empty. Searching then shows "No matching songs" with no indication of why. Separately, when Google Drive is inaccessible, PDF load failures surface a raw JS error message that doesn't help the user understand the situation.

A third gap: the search input fires `renderResults` on every keystroke, with no debounce.

## Scope

- Surface a clear error message + retry button when the catalog fails to load
- Show a friendlier message when a PDF fails to load (Drive inaccessible)
- Debounce the search input by 1 second

## Architecture

Two files change:

**`app/lib.js`**
- `createApp` gains three locals: `catalogStatus` (`'loading' | 'ready' | 'error'`), `catalogMessage` (string), and `catalogRetryFn` (function | null)
- New exposed method: `setCatalogStatus(status, opts = {})` where `opts` can carry `{ message, retry }`
- `renderResults` gets a guard at the top that short-circuits to an error or loading view based on `catalogStatus` before running any existing logic
- The search input listener is wrapped in a 1-second debounce (clears on each keypress, fires after 1 s of inactivity)

**`app/index.html` (inline script)**
- `loadCatalog()` is rewritten to call `setCatalogStatus` + `renderResults` at each lifecycle stage
- A `!resp.ok` check is added before `resp.json()` to catch HTTP errors (500, 503, etc.)
- The standalone `app.renderResults([], '')` call at init is removed — `loadCatalog` now handles rendering at each stage
- `showViewerError` in `openSong` gets a friendlier message for Drive failures

## Data Flow

```
App init
  → loadCatalog()
      → setCatalogStatus('loading') + renderResults([], '')   → "Loading your library…"
      → fetch /api/catalog
          success → app.catalog = data
                  → setCatalogStatus('ready') + renderResults([], '')
                                                               → "Type to search…  N songs indexed"
          failure → setCatalogStatus('error', { retry: loadCatalog }) + renderResults([], '')
                                                               → error message + Retry button

User clicks Retry
  → loadCatalog() called again → cycle repeats from loading state

User types in search box
  → debounce timer reset (1 s)
  → after 1 s of inactivity → renderResults(searchSongs(catalog, q), q)
      catalogStatus === 'loading' → "Loading your library…"   (guard fires, returns early)
      catalogStatus === 'error'   → error message + Retry      (guard fires, returns early)
      catalogStatus === 'ready'   → normal search results
```

## Error Messages

| Scenario | Message |
|---|---|
| Network error (server down) | "Could not reach the server — check that it's running." |
| Non-2xx HTTP response | "Server returned an error (HTTP {status})." |
| PDF load failure (Drive) | "Failed to load PDF — Google Drive may be temporarily inaccessible." |

All catalog error states show a Retry button. The PDF error is static text only (no retry — the user can click the song again).

## Edge Cases

- **Typing during loading/error**: `renderResults` guard fires on every debounced keypress and returns early, so "No matching songs" never bleeds through.
- **Double-clicking Retry**: `loadCatalog()` immediately sets status to `'loading'` and re-renders, making double-click harmless.
- **Malformed JSON response**: `resp.json()` throws and is caught, surfacing as a network error message.
- **Debounce during error state**: The timer still fires, but the guard in `renderResults` short-circuits — no visible change.
- **Display during debounce wait**: The results panel holds whatever it last rendered; no intermediate "searching…" state.

## Testing

Existing lib.js tests in `tests/test_client.js` should be extended to cover:
- `setCatalogStatus('error', ...)` causes `renderResults` to show the error view regardless of query
- `setCatalogStatus('loading', ...)` causes `renderResults` to show the loading view
- Retry button click calls the provided retry function
- Debounce: confirm `renderResults` is not called immediately on input, is called after delay

The `loadCatalog` changes in `index.html` are covered by integration: run the app with the server stopped and confirm the error state appears.
