/* ─────────────────────────────────────────────────────────────────────────
   app.js — NutriCost frontend
   Two sections:
     1. SEARCH PAGE  (index.html)
     2. PAIR PAGE    (pair.html)
   ───────────────────────────────────────────────────────────────────────── */

const API_BASE = "http://localhost:5000";

/* ── Shared helpers ────────────────────────────────────────────────────── */

async function apiFetch(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function el(id) { return document.getElementById(id); }

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/* ══════════════════════════════════════════════════════════════════════════
   1. SEARCH PAGE
   ══════════════════════════════════════════════════════════════════════════ */

function initSearchPage() {
  const input       = el("search-input");
  const status      = el("search-status");
  const resultsList = el("results-list");
  const emptyState  = el("empty-state");

  if (!input) return; // not on search page

  // ── Render helpers ──────────────────────────────────────────────────────

  function showStatus(msg) { status.textContent = msg; }

  function renderResults(results, query) {
    resultsList.innerHTML = "";

    if (!results.length) {
      emptyState.textContent = `No results for "${query}"`;
      emptyState.classList.remove("hidden");
      resultsList.classList.add("hidden");
      showStatus("");
      return;
    }

    emptyState.classList.add("hidden");
    resultsList.classList.remove("hidden");

    results.forEach(r => {
      const btn = document.createElement("button");
      btn.className = "result-item";

      const badgeClass = r.source === "usda" ? "badge-usda" : "badge-bls";
      const badgeLabel = r.source === "usda" ? "USDA" : "BLS";
      const scoreLabel = (r.score * 100).toFixed(0) + "% match";

      btn.innerHTML = `
        <span class="badge ${badgeClass}">${badgeLabel}</span>
        <span class="result-label">${r.label}</span>
        <span class="result-category">${r.category || ""}</span>
        <span class="result-score">${scoreLabel}</span>
      `;

      btn.addEventListener("click", () => handleResultClick(r));
      resultsList.appendChild(btn);
    });

    showStatus(`${results.length} result${results.length !== 1 ? "s" : ""}`);
  }

  // ── Result click: navigate to pair.html ────────────────────────────────
  // When the user clicks a result we have one side confirmed.
  // We auto-suggest the other side by calling the appropriate suggest-pairing
  // endpoint, then navigate with both IDs in the URL.

  async function handleResultClick(result) {
    showStatus("Finding best match…");

    try {
      let blsId, fdcId;

      if (result.source === "bls") {
        blsId = result.id;
        const suggestions = await apiFetch(
          `/api/suggest-pairing/bls/${encodeURIComponent(blsId)}?limit=1`
        );
        fdcId = suggestions.usda_candidates?.[0]?.fdc_id ?? "";
      } else {
        fdcId = result.id;
        const suggestions = await apiFetch(
          `/api/suggest-pairing/usda/${encodeURIComponent(fdcId)}?limit=1`
        );
        blsId = suggestions.bls_candidates?.[0]?.series_id ?? "";
      }

      const params = new URLSearchParams();
      if (blsId) params.set("bls", blsId);
      if (fdcId) params.set("fdc", fdcId);
      window.location.href = `pair.html?${params.toString()}`;

    } catch (err) {
      showStatus(`Could not find a match: ${err.message}`);
    }
  }

  // ── Search with debounce ───────────────────────────────────────────────

  const doSearch = debounce(async (query) => {
    const q = query.trim();

    if (!q) {
      emptyState.textContent = "No results yet — start typing above";
      emptyState.classList.remove("hidden");
      resultsList.classList.add("hidden");
      showStatus("Type to explore nutrition and price data");
      return;
    }

    showStatus("Searching…");

    try {
      const data = await apiFetch(
        `/api/search?q=${encodeURIComponent(q)}&limit=15`
      );
      renderResults(data.results, q);
    } catch (err) {
      showStatus(`Search failed: ${err.message}`);
    }
  }, 280); // 280 ms debounce — fast enough to feel live, light on the server

  input.addEventListener("input", (e) => doSearch(e.target.value));
  input.focus();
}


/* ══════════════════════════════════════════════════════════════════════════
   2. PAIR PAGE
   ══════════════════════════════════════════════════════════════════════════ */

function initPairPage() {
  const pairContent = el("pair-content");
  if (!pairContent) return; // not on pair page

  const params  = new URLSearchParams(window.location.search);
  const blsId   = params.get("bls") || "";
  const fdcId   = params.get("fdc") || "";

  // ── State ──────────────────────────────────────────────────────────────
  let currentBls = blsId;
  let currentFdc = fdcId;

  // ── Render helpers ──────────────────────────────────────────────────────

  function showLoading(on) {
    el("pair-loading").classList.toggle("hidden", !on);
    pairContent.classList.toggle("hidden", on);
  }

  function showError(msg) {
    const errEl = el("pair-error");
    errEl.textContent = msg;
    errEl.classList.remove("hidden");
    el("pair-loading").classList.add("hidden");
    pairContent.classList.add("hidden");
  }

  function renderNutrients(nutrients) {
    const grid = el("nutrient-grid");
    const LABELS = {
      protein:   "Protein",
      energy:    "Energy",
      fat:       "Fat",
      carbs:     "Carbs",
      fiber:     "Fiber",
      sodium:    "Sodium",
    };
    grid.innerHTML = Object.entries(LABELS)
      .filter(([key]) => nutrients[key])
      .map(([key, label]) => {
        const n = nutrients[key];
        return `
          <div class="nutrient-row">
            <span class="nutrient-name">${label}</span>
            <span class="nutrient-value">${n.value} ${n.unit}</span>
          </div>`;
      })
      .join("");
  }

  function renderMetrics(derived) {
    const grid = el("metrics-grid");
    if (!derived || !Object.keys(derived).length) {
      el("metrics-card").classList.add("hidden");
      return;
    }

    const LABELS = {
      protein_per_dollar:  ["g protein", "per $1"],
      calories_per_dollar: ["kcal", "per $1"],
      fat_per_dollar:      ["g fat", "per $1"],
      fiber_per_dollar:    ["g fiber", "per $1"],
    };

    grid.innerHTML = Object.entries(LABELS)
      .filter(([key]) => derived[key])
      .map(([key, [unit, sub]]) => {
        const val = derived[key].value.toFixed(1);
        return `
          <div class="metric-item">
            <div class="metric-value">${val}</div>
            <div class="metric-label">${unit}<br>${sub}</div>
          </div>`;
      })
      .join("");
  }

  function renderPair(data) {
    // BLS panel
    el("bls-item-name").textContent  = data.bls.item || "—";
    el("bls-area").textContent       = data.bls.area || "—";

    if (data.bls.price) {
      el("bls-price").textContent       = `$${data.bls.price.value.toFixed(3)}`;
      el("bls-price-detail").textContent =
        `per 100g · source: $${data.bls.price.source_value.toFixed(2)}/lb · ${data.bls.price.reference_period}`;
    } else {
      el("bls-price").textContent       = "No price data";
      el("bls-price-detail").textContent = "";
    }

    // USDA panel
    el("usda-description").textContent = data.description || "—";
    el("usda-category").textContent    = data.nutrients ? data.foodCategory || "" : "";
    renderNutrients(data.nutrients || {});

    // Derived metrics
    renderMetrics(data.derivedMetrics);

    // Warning
    const warnEl = el("pair-warning");
    const msg = data.pairingNotes?.warning;
    if (msg) {
      warnEl.textContent = "⚠ " + msg;
      warnEl.classList.remove("hidden");
    } else {
      warnEl.classList.add("hidden");
    }

    // Meta
    el("pair-meta").textContent =
      `fdc_id: ${data.fdc_id} · series_id: ${data.bls.series_id} · schema v${data.metadata?.schemaVersion}`;
  }

  // ── Load pair data ──────────────────────────────────────────────────────

  async function loadPair(blsId, fdcId) {
    if (!blsId || !fdcId) {
      showError("Missing series_id or fdc_id. Go back to search and pick a result.");
      return;
    }

    showLoading(true);
    try {
      const data = await apiFetch(
        `/api/pair?series_id=${encodeURIComponent(blsId)}&fdc_id=${encodeURIComponent(fdcId)}`
      );
      renderPair(data);
      showLoading(false);
    } catch (err) {
      showError(`Could not load pair: ${err.message}`);
    }
  }

  // ── Swap: BLS side ──────────────────────────────────────────────────────

  el("swap-bls-btn").addEventListener("click", async () => {
    const dropdown = el("swap-bls-list");
    const isOpen   = dropdown.classList.contains("open");

    if (isOpen) {
      dropdown.classList.remove("open");
      return;
    }

    dropdown.classList.add("open");
    dropdown.innerHTML = `<div class="swap-loading">Loading alternatives…</div>`;

    try {
      const data = await apiFetch(
        `/api/suggest-pairing/bls/${encodeURIComponent(currentBls)}?limit=6`
      );

      const options = data.similar_bls || [];
      if (!options.length) {
        dropdown.innerHTML = `<div class="swap-loading">No similar BLS series found.</div>`;
        return;
      }

      dropdown.innerHTML = options.map(s => `
        <button class="swap-option" data-series="${s.series_id}">
          ${s.item_name}
        </button>
      `).join("");

      dropdown.querySelectorAll(".swap-option").forEach(btn => {
        btn.addEventListener("click", () => {
          currentBls = btn.dataset.series;
          dropdown.classList.remove("open");
          updateURL();
          loadPair(currentBls, currentFdc);
        });
      });

    } catch (err) {
      dropdown.innerHTML = `<div class="swap-loading">Error: ${err.message}</div>`;
    }
  });

  // ── Swap: USDA side ──────────────────────────────────────────────────────

  el("swap-usda-btn").addEventListener("click", async () => {
    const dropdown = el("swap-usda-list");
    const isOpen   = dropdown.classList.contains("open");

    if (isOpen) {
      dropdown.classList.remove("open");
      return;
    }

    dropdown.classList.add("open");
    dropdown.innerHTML = `<div class="swap-loading">Loading alternatives…</div>`;

    try {
      const data = await apiFetch(
        `/api/suggest-pairing/usda/${encodeURIComponent(currentFdc)}?limit=6`
      );

      const options = data.similar_usda || [];
      if (!options.length) {
        dropdown.innerHTML = `<div class="swap-loading">No similar USDA foods found.</div>`;
        return;
      }

      dropdown.innerHTML = options.map(f => `
        <button class="swap-option" data-fdc="${f.fdc_id}">
          ${f.description}
        </button>
      `).join("");

      dropdown.querySelectorAll(".swap-option").forEach(btn => {
        btn.addEventListener("click", () => {
          currentFdc = btn.dataset.fdc;
          dropdown.classList.remove("open");
          updateURL();
          loadPair(currentBls, currentFdc);
        });
      });

    } catch (err) {
      dropdown.innerHTML = `<div class="swap-loading">Error: ${err.message}</div>`;
    }
  });

  // ── Keep URL in sync when user swaps ───────────────────────────────────

  function updateURL() {
    const p = new URLSearchParams({ bls: currentBls, fdc: currentFdc });
    history.replaceState(null, "", `pair.html?${p.toString()}`);
  }

  // ── Boot ───────────────────────────────────────────────────────────────
  loadPair(currentBls, currentFdc);
}


/* ── Route to the right init based on which page we're on ─────────────── */
document.addEventListener("DOMContentLoaded", () => {
  initSearchPage();
  initPairPage();
});
