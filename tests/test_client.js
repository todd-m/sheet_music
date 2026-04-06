/**
 * Client-side JS tests using Node's built-in test runner + jsdom.
 *
 * Run: node --test tests/test_client.js
 *   or: make test-js
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const libPath = resolve(__dirname, '..', 'app', 'lib.js');
const libSrc = readFileSync(libPath, 'utf-8');

// ── Helpers ──

/** Minimal HTML shell matching the app's DOM structure. */
const HTML_SHELL = `<!DOCTYPE html>
<html><body>
  <header>
    <h1>Sheet Music Library</h1>
    <div><input type="text" id="search"><span id="result-count"></span></div>
  </header>
  <div class="main">
    <div class="results-panel" id="results-panel">
      <div class="fs-search-icon" id="fs-search-icon">search</div>
      <div class="fs-tiles" id="fs-tiles"></div>
      <div class="no-results" id="empty-state">Type to search your library</div>
    </div>
    <div class="viewer-panel" id="viewer-panel">
      <div class="viewer-empty" id="viewer-empty">Select a song to view</div>
    </div>
  </div>
</body></html>`;

const SAMPLE_CATALOG = {
  volumes: {
    Realbk1: { name: 'The Real Book Vol 1', driveFileId: 'abc123', pageOffset: 5 },
  },
  songs: [
    { title: 'All Of Me', volumeId: 'Realbk1', nominalPage: 15, source: 'master-index' },
    { title: 'Autumn Leaves', volumeId: 'Realbk1', nominalPage: 30, source: 'master-index' },
    { title: 'Blue Bossa', volumeId: 'Realbk1', nominalPage: 42, source: 'master-index' },
    { title: 'All The Things You Are', volumeId: 'Realbk1', nominalPage: 18, source: 'master-index' },
    { title: 'Stella By Starlight', volumeId: 'Realbk1', nominalPage: 100, source: 'master-index' },
  ],
};

/**
 * Load lib.js into a jsdom window and return the exports.
 * We use a data URL with a dynamic import so that the ES module
 * is evaluated in the jsdom context.
 */
async function loadLib() {
  const dom = new JSDOM(HTML_SHELL, {
    url: 'http://localhost',
    runScripts: 'dangerously',
    resources: 'usable',
  });

  // Evaluate lib.js source as a module-like script by wrapping in an IIFE
  // that assigns exports to window.__lib.
  const wrappedSrc = `
    (function() {
      ${libSrc
        .replace(/^export /gm, '')           // strip export keywords
        .replace(/^import .*/gm, '')}        // strip import statements (none expected, but safe)
      window.__lib = { escapeHtml, escapeRegex, highlightMatch, searchSongs, createApp };
    })();
  `;
  dom.window.eval(wrappedSrc);

  return { dom, lib: dom.window.__lib };
}


// ═══════════════════════════════════════════
// Pure function tests
// ═══════════════════════════════════════════

describe('escapeHtml', () => {
  let lib;
  beforeEach(async () => { ({ lib } = await loadLib()); });

  it('escapes ampersands', () => {
    assert.equal(lib.escapeHtml('A & B'), 'A &amp; B');
  });

  it('escapes angle brackets', () => {
    assert.equal(lib.escapeHtml('<div>'), '&lt;div&gt;');
  });

  it('passes through safe strings', () => {
    assert.equal(lib.escapeHtml('hello world'), 'hello world');
  });
});


describe('escapeRegex', () => {
  let lib;
  beforeEach(async () => { ({ lib } = await loadLib()); });

  it('escapes special regex characters', () => {
    const result = lib.escapeRegex('foo.bar+baz');
    assert.equal(result, 'foo\\.bar\\+baz');
  });

  it('escapes parentheses and brackets', () => {
    const result = lib.escapeRegex('(a)[b]{c}');
    assert.equal(result, '\\(a\\)\\[b\\]\\{c\\}');
  });
});


describe('highlightMatch', () => {
  let lib;
  beforeEach(async () => { ({ lib } = await loadLib()); });

  it('returns escaped title when query is empty', () => {
    assert.equal(lib.highlightMatch('<script>', ''), '&lt;script&gt;');
  });

  it('wraps matching term in mark tags', () => {
    const result = lib.highlightMatch('Autumn Leaves', 'autumn');
    assert.equal(result, '<mark>Autumn</mark> Leaves');
  });

  it('highlights multiple terms', () => {
    const result = lib.highlightMatch('All The Things You Are', 'all are');
    assert.ok(result.includes('<mark>All</mark>'));
    assert.ok(result.includes('<mark>Are</mark>'));
  });

  it('is case insensitive', () => {
    const result = lib.highlightMatch('Blue Bossa', 'BLUE');
    assert.equal(result, '<mark>Blue</mark> Bossa');
  });
});


describe('searchSongs', () => {
  let lib;
  beforeEach(async () => { ({ lib } = await loadLib()); });

  it('returns empty for blank query', () => {
    assert.equal(lib.searchSongs(SAMPLE_CATALOG, '').length, 0);
    assert.equal(lib.searchSongs(SAMPLE_CATALOG, '   ').length, 0);
  });

  it('finds songs matching a single term', () => {
    const results = lib.searchSongs(SAMPLE_CATALOG, 'blue');
    assert.equal(results.length, 1);
    assert.equal(results[0].title, 'Blue Bossa');
  });

  it('matches multiple terms (all must appear)', () => {
    const results = lib.searchSongs(SAMPLE_CATALOG, 'all me');
    assert.equal(results.length, 1);
    assert.equal(results[0].title, 'All Of Me');
  });

  it('returns no results when a term does not match', () => {
    const results = lib.searchSongs(SAMPLE_CATALOG, 'blue leaves');
    assert.equal(results.length, 0);
  });

  it('ranks starts-with matches higher', () => {
    const results = lib.searchSongs(SAMPLE_CATALOG, 'all');
    assert.ok(results.length >= 2);
    // "All Of Me" and "All The Things You Are" both start with "All"
    // They should appear before any song that merely contains "all" mid-title
    assert.ok(results[0].title.startsWith('All'));
    assert.ok(results[1].title.startsWith('All'));
  });

  it('is case insensitive', () => {
    const results = lib.searchSongs(SAMPLE_CATALOG, 'STELLA');
    assert.equal(results.length, 1);
    assert.equal(results[0].title, 'Stella By Starlight');
  });
});


// ═══════════════════════════════════════════
// DOM-dependent tests (via createApp)
// ═══════════════════════════════════════════

describe('renderResults', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('shows empty state for blank query', () => {
    app.renderResults([], '');
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.equal(emptyState.textContent, 'Type to search your library');
    assert.notEqual(emptyState.style.display, 'none');
  });

  it('shows "no matching songs" for empty results with query', () => {
    app.renderResults([], 'zzzzz');
    const emptyState = dom.window.document.getElementById('empty-state');
    assert.equal(emptyState.textContent, 'No matching songs');
  });

  it('creates result-item divs for matches', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'all');
    app.renderResults(songs, 'all');
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.ok(items.length >= 2);
  });

  it('shows correct result count', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'all');
    app.renderResults(songs, 'all');
    const count = dom.window.document.getElementById('result-count');
    assert.ok(count.textContent.includes(String(songs.length)));
  });

  it('shows singular "result" for single match', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'blue');
    app.renderResults(songs, 'blue');
    const count = dom.window.document.getElementById('result-count');
    assert.ok(count.textContent.includes('1 result'));
    assert.ok(!count.textContent.includes('results'));
  });

  it('clears previous results on new search', () => {
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'all'), 'all');
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'blue'), 'blue');
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 1);
  });

  it('displays volume name and page in meta', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'blue');
    app.renderResults(songs, 'blue');
    const meta = dom.window.document.querySelector('.result-meta');
    assert.ok(meta.textContent.includes('The Real Book Vol 1'));
    assert.ok(meta.textContent.includes('42'));
  });
});


describe('search input wiring', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('typing in search input renders results', () => {
    const input = dom.window.document.getElementById('search');
    input.value = 'autumn';
    input.dispatchEvent(new dom.window.Event('input'));
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(items.length, 1);
  });
});


// ═══════════════════════════════════════════
// Fullscreen mode tests
// ═══════════════════════════════════════════

describe('toggleFullscreen', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('adds fullscreen class to body', () => {
    app.toggleFullscreen();
    assert.ok(dom.window.document.body.classList.contains('fullscreen'));
    assert.equal(app.isFullscreen, true);
  });

  it('removes fullscreen class on second toggle', () => {
    app.toggleFullscreen();
    app.toggleFullscreen();
    assert.ok(!dom.window.document.body.classList.contains('fullscreen'));
    assert.equal(app.isFullscreen, false);
  });

  it('accepts force=true', () => {
    app.toggleFullscreen(true);
    assert.equal(app.isFullscreen, true);
    app.toggleFullscreen(true);
    assert.equal(app.isFullscreen, true);
  });

  it('accepts force=false', () => {
    app.toggleFullscreen(true);
    app.toggleFullscreen(false);
    assert.equal(app.isFullscreen, false);
  });

  it('updates button text when viewer is active', () => {
    app.showViewer();
    app.toggleFullscreen(true);
    const btn = dom.window.document.getElementById('btn-fullscreen');
    assert.equal(btn.textContent, 'Exit');
    app.toggleFullscreen(false);
    assert.equal(btn.textContent, 'Focus');
  });
});


describe('buildTiles', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('creates a tile for each result item', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'all');
    app.renderResults(songs, 'all');
    app.buildTiles();
    const tiles = dom.window.document.querySelectorAll('.fs-tile');
    const items = dom.window.document.querySelectorAll('.result-item');
    assert.equal(tiles.length, items.length);
  });

  it('tiles have short labels (max 6 chars)', () => {
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'stella'), 'stella');
    app.buildTiles();
    const tile = dom.window.document.querySelector('.fs-tile');
    assert.ok(tile.textContent.length <= 6);
  });

  it('tiles have full title as tooltip', () => {
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'stella'), 'stella');
    app.buildTiles();
    const tile = dom.window.document.querySelector('.fs-tile');
    assert.equal(tile.title, 'Stella By Starlight');
  });

  it('marks active tile when result is active', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'blue');
    app.renderResults(songs, 'blue');
    // Simulate clicking the result item to make it active
    const item = dom.window.document.querySelector('.result-item');
    item.click();
    app.buildTiles();
    const tile = dom.window.document.querySelector('.fs-tile');
    assert.ok(tile.classList.contains('active'));
  });

  it('clicking a tile activates it and deactivates others', () => {
    const songs = lib.searchSongs(SAMPLE_CATALOG, 'all');
    app.renderResults(songs, 'all');
    app.buildTiles();
    const tiles = dom.window.document.querySelectorAll('.fs-tile');
    assert.ok(tiles.length >= 2);
    tiles[1].click();
    assert.ok(tiles[1].classList.contains('active'));
    assert.ok(!tiles[0].classList.contains('active'));
  });

  it('entering fullscreen auto-builds tiles', () => {
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'all'), 'all');
    app.toggleFullscreen(true);
    const tiles = dom.window.document.querySelectorAll('.fs-tile');
    assert.ok(tiles.length >= 2);
  });

  it('tiles rebuild when search changes in fullscreen', () => {
    app.toggleFullscreen(true);
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'all'), 'all');
    const tilesAfterAll = dom.window.document.querySelectorAll('.fs-tile').length;
    app.renderResults(lib.searchSongs(SAMPLE_CATALOG, 'blue'), 'blue');
    const tilesAfterBlue = dom.window.document.querySelectorAll('.fs-tile').length;
    assert.equal(tilesAfterBlue, 1);
    assert.ok(tilesAfterAll > tilesAfterBlue);
  });

  it('tiles are empty when no results', () => {
    app.toggleFullscreen(true);
    app.renderResults([], 'zzz');
    const tiles = dom.window.document.querySelectorAll('.fs-tile');
    assert.equal(tiles.length, 0);
  });
});


describe('search icon exits fullscreen', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('clicking search icon exits fullscreen', () => {
    app.toggleFullscreen(true);
    assert.equal(app.isFullscreen, true);
    dom.window.document.getElementById('fs-search-icon').click();
    assert.equal(app.isFullscreen, false);
    assert.ok(!dom.window.document.body.classList.contains('fullscreen'));
  });

  it('clicking search icon focuses the search input', () => {
    app.toggleFullscreen(true);
    dom.window.document.getElementById('fs-search-icon').click();
    assert.equal(dom.window.document.activeElement, dom.window.document.getElementById('search'));
  });
});


describe('showViewer', () => {
  let dom, lib, app;
  beforeEach(async () => {
    ({ dom, lib } = await loadLib());
    app = lib.createApp(dom.window.document, { catalog: SAMPLE_CATALOG });
  });

  it('renders toolbar with navigation and fullscreen buttons', () => {
    app.showViewer();
    assert.ok(dom.window.document.getElementById('btn-prev'));
    assert.ok(dom.window.document.getElementById('btn-next'));
    assert.ok(dom.window.document.getElementById('btn-zoom-out'));
    assert.ok(dom.window.document.getElementById('btn-zoom-in'));
    assert.ok(dom.window.document.getElementById('btn-fullscreen'));
  });

  it('fullscreen button shows "Focus" by default', () => {
    app.showViewer();
    const btn = dom.window.document.getElementById('btn-fullscreen');
    assert.equal(btn.textContent, 'Focus');
  });

  it('fullscreen button shows "Exit" when already in fullscreen', () => {
    app.toggleFullscreen(true);
    app.showViewer();
    const btn = dom.window.document.getElementById('btn-fullscreen');
    assert.equal(btn.textContent, 'Exit');
  });

  it('clicking fullscreen button toggles fullscreen', () => {
    app.showViewer();
    dom.window.document.getElementById('btn-fullscreen').click();
    assert.equal(app.isFullscreen, true);
    assert.ok(dom.window.document.body.classList.contains('fullscreen'));
  });

  it('renders canvas container', () => {
    app.showViewer();
    assert.ok(dom.window.document.getElementById('pdf-canvas'));
    assert.ok(dom.window.document.getElementById('viewer-canvas-container'));
  });
});
