/**
 * Shared library functions for the sheet music app.
 * Extracted so they can be tested independently and imported by index.html.
 */

export function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

export function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function highlightMatch(title, query) {
  if (!query.trim()) return escapeHtml(title);
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  let result = escapeHtml(title);
  for (const term of terms) {
    const regex = new RegExp(`(${escapeRegex(term)})`, 'gi');
    result = result.replace(regex, '<mark>$1</mark>');
  }
  return result;
}

export function searchSongs(catalog, query) {
  if (!query.trim()) return [];
  const terms = query.toLowerCase().split(/\s+/);
  const scored = [];
  for (const song of catalog.songs) {
    const titleLower = song.title.toLowerCase();
    let match = true;
    let score = 0;
    for (const term of terms) {
      const idx = titleLower.indexOf(term);
      if (idx === -1) { match = false; break; }
      if (idx === 0) score += 10;
      score += (1 / (idx + 1));
    }
    if (match) {
      scored.push({ song, score });
    }
  }
  scored.sort((a, b) => b.score - a.score || a.song.title.localeCompare(b.song.title));
  return scored.map(s => s.song);
}

/**
 * Create the app controller. Requires a DOM document and options.
 * Separating construction from side effects makes DOM-dependent logic testable.
 */
export function createApp(doc, { catalog: initialCatalog, onOpenSong } = {}) {
  let catalog = initialCatalog || { volumes: {}, songs: [] };
  let isFullscreen = false;
  let activeResult = null;

  const resultsPanel = doc.getElementById('results-panel');
  const emptyState = doc.getElementById('empty-state');
  const resultCount = doc.getElementById('result-count');
  const searchInput = doc.getElementById('search');
  const viewerPanel = doc.getElementById('viewer-panel');

  function renderResults(songs, query) {
    resultsPanel.querySelectorAll('.result-item').forEach(el => el.remove());

    if (!query.trim()) {
      emptyState.style.display = '';
      emptyState.textContent = 'Type to search your library';
      resultCount.textContent = `${catalog.songs.length} songs indexed`;
      return;
    }
    if (songs.length === 0) {
      emptyState.style.display = '';
      emptyState.textContent = 'No matching songs';
      resultCount.textContent = '';
      return;
    }

    emptyState.style.display = 'none';
    resultCount.textContent = `${songs.length} result${songs.length === 1 ? '' : 's'}`;

    for (const song of songs) {
      const vol = catalog.volumes[song.volumeId] || {};
      const div = doc.createElement('div');
      div.className = 'result-item';
      div.innerHTML = `
        <div class="result-title">${highlightMatch(song.title, query)}</div>
        <div class="result-meta">
          <span class="volume-name">${escapeHtml(vol.name || song.volumeId)}</span>
          &middot; p. ${song.nominalPage}
          ${song.composer ? ' &middot; ' + escapeHtml(song.composer) : ''}
        </div>
      `;
      div.addEventListener('click', () => {
        if (activeResult) activeResult.classList.remove('active');
        div.classList.add('active');
        activeResult = div;
        if (onOpenSong) onOpenSong(song, div);
      });
      resultsPanel.appendChild(div);
    }

    if (isFullscreen) buildTiles();
  }

  function showViewer() {
    viewerPanel.innerHTML = `
      <div class="viewer-toolbar">
        <button id="btn-prev" title="Previous page">&larr; Prev</button>
        <button id="btn-next" title="Next page">Next &rarr;</button>
        <button id="btn-zoom-out" title="Zoom out">&minus;</button>
        <button id="btn-zoom-in" title="Zoom in">+</button>
        <span class="page-info" id="page-info"></span>
        <button id="btn-fullscreen" class="btn-fullscreen" title="Toggle fullscreen">${isFullscreen ? 'Exit' : 'Focus'}</button>
      </div>
      <div id="viewer-canvas-container"><canvas id="pdf-canvas"></canvas></div>
    `;
    doc.getElementById('btn-fullscreen').addEventListener('click', () => toggleFullscreen());
  }

  function toggleFullscreen(force) {
    isFullscreen = (force !== undefined) ? force : !isFullscreen;
    doc.body.classList.toggle('fullscreen', isFullscreen);
    if (isFullscreen) buildTiles();
    const btn = doc.getElementById('btn-fullscreen');
    if (btn) btn.textContent = isFullscreen ? 'Exit' : 'Focus';
  }

  function buildTiles() {
    const container = doc.getElementById('fs-tiles');
    container.innerHTML = '';
    const items = resultsPanel.querySelectorAll('.result-item');
    items.forEach(item => {
      const title = item.querySelector('.result-title')?.textContent || '?';
      const shortLabel = title.substring(0, 6).trim();
      const tile = doc.createElement('div');
      tile.className = 'fs-tile' + (item.classList.contains('active') ? ' active' : '');
      tile.textContent = shortLabel;
      tile.title = title;
      tile.addEventListener('click', () => {
        item.click();
        container.querySelectorAll('.fs-tile').forEach(t => t.classList.remove('active'));
        tile.classList.add('active');
      });
      container.appendChild(tile);
    });
  }

  // Wire search icon
  doc.getElementById('fs-search-icon').addEventListener('click', () => {
    toggleFullscreen(false);
    searchInput.focus();
  });

  // Wire search input
  searchInput.addEventListener('input', () => {
    const q = searchInput.value;
    const results = searchSongs(catalog, q);
    renderResults(results, q);
  });

  return {
    get catalog() { return catalog; },
    set catalog(c) { catalog = c; },
    get isFullscreen() { return isFullscreen; },
    renderResults,
    showViewer,
    toggleFullscreen,
    buildTiles,
    search(q) { return searchSongs(catalog, q); },
  };
}
