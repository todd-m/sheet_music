# Offline Mode Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a clear error message with a Retry button when the catalog fails to load, show a friendlier message when a PDF fails to load, and debounce the search input by 1 second.

**Architecture:** Add `catalogStatus` state and `setCatalogStatus()` to `createApp` in `lib.js`; `renderResults` checks status before running search logic. `loadCatalog()` in `index.html` is rewritten to set status at each lifecycle stage and call `renderResults` itself. The search input listener is wrapped in a configurable debounce (default 1000ms, 0ms in tests).

**Tech Stack:** Vanilla JS (ES modules), jsdom (tests), Node.js built-in test runner

---

## File Map

- **Modify:** `app/lib.js` — add `catalogStatus` state, `setCatalogStatus()`, debounce option
- **Modify:** `app/index.html` — rewrite `loadCatalog()`, improve PDF error message, add `.btn-retry` CSS
- **Modify:** `tests/test_client.js` — add catalog status tests, update wiring tests for debounce

---

### Task 1: Add catalog status state and guard to `lib.js`

**Files:**
- Modify: `app/lib.js`
- Test: `tests/test_client.js`

- [ ] **Step 1: Add catalog status tests to `tests/test_client.js`**

Add this new `describe` block after the existing `renderResults` describe block (after line 248):

```js
describe('catalog status', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('shows loading message when status is loading', () => {
    app.setCatalogStatus('loading');
    app.renderResults([], '');
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.ok(emptyState.textContent.includes('Loading'));
  });

  it('shows loading message with a non-empty query', () => {
    app.setCatalogStatus('loading');
    app.renderResults([], 'autumn');
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.ok(emptyState.textContent.includes('Loading'));
  });

  it('shows error message when status is error', () => {
    app.setCatalogStatus('error', { message: 'Could not reach the server — check that it\'s running.' });
    app.renderResults([], '');
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.ok(emptyState.textContent.includes('Could not reach the server'));
  });

  it('shows retry button when status is error', () => {
    app.setCatalogStatus('error', { message: 'Could not reach the server — check that it\'s running.' });
    app.renderResults([], '');
    const retryBtn = dom.window.document.querySelector('.btn-retry');
    assert.ok(retryBtn, 'retry button should be present');
  });

  it('retry button calls the retry function', () => {
    let retryCalled = false;
    app.setCatalogStatus('error', {
      message: 'Server error',
      retry: () => { retryCalled = true; },
    });
    app.renderResults([], '');
    dom.window.document.querySelector('.btn-retry').click();
    assert.ok(retryCalled);
  });

  it('error state shows regardless of query', () => {
    app.setCatalogStatus('error', { message: 'Server error' });
    app.renderResults([], 'autumn');
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 0);
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.ok(emptyState.textContent.includes('Server error'));
  });

  it('shows normal results when status is ready', () => {
    app.setCatalogStatus('ready');
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'all');
    app.renderResults(songs, 'all');
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.ok(items.length >= 2);
  });

  it('clears error state when status returns to ready', () => {
    app.setCatalogStatus('error', { message: 'Server error' });
    app.renderResults([], '');
    app.setCatalogStatus('ready');
    app.renderResults([], '');
    const retryBtn = dom.window.document.querySelector('.btn-retry');
    assert.equal(retryBtn, null, 'retry button should be gone after recovery');
  });
});
```

- [ ] **Step 2: Run tests to confirm new tests fail**

```bash
node --test tests/test_client.js 2>&1 | grep -E '(catalog status|FAIL|Error)'
```

Expected: failures for `catalog status` tests with `TypeError: app.setCatalogStatus is not a function`

- [ ] **Step 3: Add catalog status locals and `setCatalogStatus` to `createApp` in `app/lib.js`**

In `createApp`, add three locals after `let activeResult = null;` (after line 53):

```js
let catalogStatus = 'ready';
let catalogMessage = '';
let catalogRetryFn = null;
```

Add this function inside `createApp`, before `renderResults`:

```js
function setCatalogStatus(status, opts = {}) {
  catalogStatus = status;
  catalogMessage = opts.message || '';
  catalogRetryFn = opts.retry || null;
}
```

- [ ] **Step 4: Insert status guard blocks into `renderResults` in `app/lib.js`**

In `renderResults`, after the line:
```js
resultsPanel.querySelectorAll('.result-item').forEach(el => el.remove());
```
and before the existing `if (!query.trim()) {` line, insert these two guard blocks:

```js
  if (catalogStatus === 'loading') {
    emptyState.style.display = '';
    emptyState.textContent = 'Loading your library…';
    resultCount.textContent = '';
    return;
  }

  if (catalogStatus === 'error') {
    emptyState.style.display = '';
    emptyState.innerHTML = '';
    const msgSpan = doc.createElement('span');
    msgSpan.textContent = catalogMessage;
    emptyState.appendChild(msgSpan);
    if (catalogRetryFn) {
      const btn = doc.createElement('button');
      btn.className = 'btn-retry';
      btn.textContent = 'Retry';
      btn.addEventListener('click', catalogRetryFn);
      emptyState.appendChild(btn);
    }
    resultCount.textContent = '';
    return;
  }
```

Nothing else in `renderResults` changes.

- [ ] **Step 5: Expose `setCatalogStatus` in the returned object**

In the `return { ... }` at the bottom of `createApp`, add `setCatalogStatus` alongside the existing methods:

```js
return {
  get catalog() { return catalog; },
  set catalog(c) { catalog = c; },
  get isFullscreen() { return isFullscreen; },
  renderResults,
  showViewer,
  toggleFullscreen,
  buildTiles,
  setCatalogStatus,
  search(q) { return searchSongs(catalog, q); },
};
```

- [ ] **Step 6: Run tests to confirm all pass**

```bash
node --test tests/test_client.js
```

Expected: all tests pass, no failures

- [ ] **Step 7: Commit**

```bash
git add app/lib.js tests/test_client.js
git commit -m "feat: add catalog status state to createApp for offline error display"
```

---

### Task 2: Debounce the search input in `lib.js`

**Files:**
- Modify: `app/lib.js`
- Modify: `tests/test_client.js`

- [ ] **Step 1: Update existing `createApp` test calls to pass `debounceMs: 0`**

Every `lib.createApp(...)` call in `tests/test_client.js` must receive `debounceMs: 0` so the debounce is bypassed in tests. There are six `beforeEach` blocks that call `createApp`. Change each one from:

```js
app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
```

to:

```js
app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG, debounceMs: 0 });
```

The six locations are in the `beforeEach` of: `renderResults`, `catalog status`, `search input wiring`, `toggleFullscreen`, `buildTiles`, `search icon exits fullscreen`, and `showViewer` (7 total — check the file for any missed).

- [ ] **Step 2: Update the existing wiring test to be async (it now needs to wait for the debounce)**

Replace the existing test in `describe('search input wiring', ...)`:

```js
it('typing in search input renders results', async () => {
  const input = dom.window.document.getElementById('search');
  input.value = 'autumn';
  input.dispatchEvent(new dom.window.Event('input'));
  await new Promise(r => setTimeout(r, 50));
  const items = dom.window.document.querySelectorAll('.result-item');
  assert.equal(items.length, 1);
});
```

- [ ] **Step 3: Add debounce behavior tests**

Add a new `describe` block after `search input wiring`:

```js
describe('search input debounce', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    // Use 100ms debounce so tests can verify timing without long waits
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG, debounceMs: 100 });
  });

  it('does not render immediately on input', () => {
    const input = dom.window.document.getElementById('search');
    input.value = 'autumn';
    input.dispatchEvent(new dom.window.Event('input'));
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 0, 'should not render before debounce timeout');
  });

  it('renders results after the debounce period elapses', async () => {
    const input = dom.window.document.getElementById('search');
    input.value = 'autumn';
    input.dispatchEvent(new dom.window.Event('input'));
    await new Promise(r => setTimeout(r, 150));
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 1);
  });

  it('cancels a pending render when typing continues', async () => {
    const input = dom.window.document.getElementById('search');
    // First keypress
    input.value = 'aut';
    input.dispatchEvent(new dom.window.Event('input'));
    await new Promise(r => setTimeout(r, 40));
    // Second keypress resets the timer
    input.value = 'autumn';
    input.dispatchEvent(new dom.window.Event('input'));
    // Debounce has not fired yet (40ms into second 100ms window)
    await new Promise(r => setTimeout(r, 40));
    let items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 0, 'should not have rendered mid-debounce');
    // Now let the debounce complete
    await new Promise(r => setTimeout(r, 80));
    items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 1);
  });
});
```

- [ ] **Step 4: Run tests to confirm new debounce tests fail**

```bash
node --test tests/test_client.js 2>&1 | grep -E '(debounce|FAIL|Error)'
```

Expected: `search input debounce` tests fail (no debounce implemented yet); the updated wiring test may also fail

- [ ] **Step 5: Add `debounceMs` option and wrap the search listener in `createApp`**

Change the destructuring at the top of `createApp` (line 51) from:

```js
export function createApp(doc, { catalog: initialCatalog, onOpenSong } = {}) {
```

to:

```js
export function createApp(doc, { catalog: initialCatalog, onOpenSong, debounceMs = 1000 } = {}) {
```

Then replace the search input event listener (lines 155–159) with:

```js
let searchTimer = null;
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const q = searchInput.value;
    const results = searchSongs(catalog, q);
    renderResults(results, q);
  }, debounceMs);
});
```

- [ ] **Step 6: Run all tests to confirm they pass**

```bash
node --test tests/test_client.js
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add app/lib.js tests/test_client.js
git commit -m "feat: debounce search input (1 s default, configurable for tests)"
```

---

### Task 3: Rewrite `loadCatalog` and improve PDF error message in `index.html`

**Files:**
- Modify: `app/index.html`

- [ ] **Step 1: Add `.btn-retry` CSS to `index.html`**

In the `<style>` block, add after the `.btn-ingest:hover` rule (after line 176):

```css
.btn-retry {
  display: block;
  margin: 12px auto 0;
  background: var(--surface2);
  color: var(--text);
  border: none;
  padding: 8px 18px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}
.btn-retry:hover { background: var(--accent); }
```

- [ ] **Step 2: Rewrite `loadCatalog` in the inline `<script>` of `index.html`**

Replace the existing `loadCatalog` function (lines 298–305):

```js
async function loadCatalog() {
  try {
    const resp = await fetch('/api/catalog');
    app.catalog = await resp.json();
  } catch (e) {
    console.error('Failed to load catalog:', e);
  }
}
```

with:

```js
async function loadCatalog() {
  app.setCatalogStatus('loading');
  app.renderResults([], '');
  try {
    const resp = await fetch('/api/catalog');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    app.catalog = await resp.json();
    app.setCatalogStatus('ready');
    app.renderResults([], '');
  } catch (e) {
    console.error('Failed to load catalog:', e);
    const message = e.message.startsWith('HTTP ')
      ? `Server returned an error (${e.message}).`
      : 'Could not reach the server — check that it\'s running.';
    app.setCatalogStatus('error', { message, retry: loadCatalog });
    app.renderResults([], '');
  }
}
```

- [ ] **Step 3: Remove the now-redundant `app.renderResults([], '')` at the bottom of the init block**

The init block at the end of the inline script currently reads:

```js
await loadCatalog();
app.renderResults([], '');
```

Change it to:

```js
await loadCatalog();
```

`loadCatalog` now calls `renderResults` itself at every stage.

- [ ] **Step 4: Improve the PDF error message in `openSong`**

Find this line inside the `catch` block of `openSong` (around line 337):

```js
showViewerError(`Failed to load PDF: ${e.message}`);
```

Replace it with:

```js
showViewerError('Failed to load PDF — Google Drive may be temporarily inaccessible.');
```

- [ ] **Step 5: Manual verification — server running**

Start the server and open the app:

```bash
uvicorn server:app --reload --port 8000
```

Open `http://localhost:8000` in a browser. Confirm:
- On load: briefly shows "Loading your library…" then transitions to "Type to search…  N songs indexed"
- Searching a tune works after a ~1 second pause after typing stops

- [ ] **Step 6: Manual verification — server offline**

Stop the server (`Ctrl-C`). Open (or refresh) `http://localhost:8000`.

Confirm:
- The results panel shows "Could not reach the server — check that it's running." with a Retry button
- Clicking Retry re-attempts the fetch (and shows the error again since server is still down)
- Restart the server, click Retry — the app recovers and shows the normal idle state

- [ ] **Step 7: Commit**

```bash
git add app/index.html
git commit -m "feat: surface catalog load errors with retry button, friendlier PDF error message"
```
