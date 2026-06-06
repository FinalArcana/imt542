# Nutrition–Cost Finder
**IMT542A Sp26 · Pete Namchaisiri**

A system that integrates USDA Foundation Foods nutrient data with BLS Average Retail Food Prices to show how foods compare in nutritional value relative to their cost. Users can search for a food, view its protein-per-dollar and calorie-per-dollar metrics, compare multiple foods side by side, and explore historical price trends — all from standardized public data sources.

---

## Table of Contents

1. [Information Story](#information-story)
2. [Project Documents](#project-documents)
3. [Data Sources](#data-sources)
4. [System Architecture](#system-architecture)
5. [How to Run](#how-to-run)
6. [API Reference](#api-reference)
7. [Output Structure](#output-structure)
8. [Quality & Performance](#quality--performance)
9. [Known Limitations](#known-limitations)

---

## Information Story

**User:** A student, researcher, or public health analyst interested in food affordability in the U.S.

**Problem:** Nutrition data and retail price data exist in separate, incompatible datasets. Comparing how nutritious a food is per dollar requires manual cross-referencing across sources that use different identifiers, units, and granularities — a task not currently supported by any single USDA or BLS endpoint.

**Solution:** This system merges USDA Foundation Foods (nutrient composition per 100g) with BLS Average Retail Food Prices (price per pound, converted to per-100g basis) into a unified, structured JSON output. Users search by food name, select from fuzzy-matched results, and receive a single record with raw nutrients, normalized price, and derived cost-efficiency metrics. Multi-food comparison and price trend endpoints support deeper analysis.

**Scope:** Covers foods present in both datasets. Metrics are descriptive only — calories and protein per dollar — and should not be interpreted as dietary or policy guidance.

---

## Project Documents

| Assignment | Description |
|---|---|
| [G2](g2_daily_information_ideas.csv) | Initial information ideas and MSIM specialization alignment |
| [G3](g3.json) | Refined project ideation — Food Nutrition vs. Cost Database selected |
| [G4](g4.pdf) | Wireframe, concepts, and proposed system structure |
| [G5](g5.txt) | FAIR principles analysis of source datasets |
| [G6](g6.md) | Availability, limitations, ethics, and societal impact |
| [G7](g7.md) | Deficiency analysis and improved information structure design |
| [G8](g8.md) | API documentation and access methodology |
| [G9](g9.md) | Test plan, quality metrics, and monitoring strategy |

---

## Data Sources

| Dataset | Source | Format | Access |
|---|---|---|---|
| USDA Foundation Foods | [https://fdc.nal.usda.gov/](https://fdc.nal.usda.gov/) | JSON (bulk download) | Public, no auth required |
| BLS Average Retail Food Prices | [https://download.bls.gov/pub/time.series/ap/](https://download.bls.gov/pub/time.series/ap/) | Tab-delimited flat files | Public, no auth required |

Both datasets are stored locally. No live external calls are made at query time.

**Unit normalization:** All nutrient values are expressed per 100g (Foundation Foods native basis). BLS prices are given per pound and converted: `price_per_100g = price_per_lb / 4.536`.

**Expected BLS files** (place in `data/`):

| File | Description |
|---|---|
| `ap.series` | Series metadata (series_id, item_code, area_code) |
| `ap.data.3.Food` | Price observations by series, year, and period |
| `ap.item` | Item code → item name lookup |
| `ap.area` | Area code → area name lookup |

---

## System Architecture

```
data/
  FoodData_Central_foundation_food_json_2025-12-18.json  ← USDA Foundation Foods bulk download
  ap.series          ← BLS series metadata
  ap.data.3.Food     ← BLS price observations
  ap.item            ← BLS item lookup
  ap.area            ← BLS area lookup

app.py               ← Flask REST API
usda_bls_bridge.py   ← Data loading, normalization, matching, and metric computation
series_access.db     ← SQLite access log (auto-created on first run)
```

**Stack:** Python (Flask), pandas, SQLite, local JSON + tab-delimited flat files, unified fuzzy search via `usda_bls_bridge`.

**Access logging:** Every call to a BLS series is recorded in `series_access.db`, enabling usage analytics and anomaly detection via `/analytics/top-series`.

---

## How to Run

### Requirements

- Python 3.9+

### Setup

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd nutrition-cost-finder

# 2. Download data files and place them in data/
#    USDA Foundation Foods bulk JSON:
#      https://fdc.nal.usda.gov/download-data
#      → FoodData_Central_foundation_food_json_2025-12-18.json
#
#    BLS Average Retail Food Prices flat files:
#      https://download.bls.gov/pub/time.series/ap/
#      → ap.series, ap.data.3.Food, ap.item, ap.area

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python app.py
```

Server runs at `http://localhost:5000` by default. The SQLite access log (`series_access.db`) is created automatically on first run.

---

## API Reference

No authentication required. All endpoints return JSON.

---

### `GET /api/search`

Unified search across both USDA Foundation Foods and BLS price series in a single call. Results are ranked by token-overlap score. Rate limited to 600 requests/minute.

| Param | Type | Default | Description |
|---|---|---|---|
| `q` | string | required | Food name to search (e.g. `chicken`) |
| `limit` | integer | 10 | Max results (capped at 50) |
| `min_score` | float | 0.3 | Minimum match score threshold |

**Example:**
```
GET /api/search?q=chicken&limit=5
```
```json
{
  "query": "chicken",
  "count": 5,
  "results": [
    { "label": "Chicken, broilers, breast, raw", "source": "usda", "id": "171077", "category": "Poultry Products", "score": 0.85 },
    { "label": "Chicken, fresh, whole, per lb.", "source": "bls",  "id": "APU0000706111", "area_name": "U.S. city average", "score": 0.81 }
  ]
}
```

Use `source` to distinguish USDA vs. BLS results. Pass `id` values to `/api/pair`.

---

### `GET /api/pair`

Core endpoint. Pairs a USDA food with a BLS price series and returns the integrated record with derived metrics.

| Param | Type | Description |
|---|---|---|
| `fdc_id` | string | USDA Foundation Foods ID (from `/api/search`) |
| `series_id` | string | BLS AP series ID (from `/api/search`) |

**Example:**
```
GET /api/pair?fdc_id=321358&series_id=APU0000706111
```

See [Output Structure](#output-structure) for the full response schema.

---

### `GET /api/nutrition/search`

Search USDA Foundation Foods only (substring match).

| Param | Type | Default | Description |
|---|---|---|---|
| `q` | string | required | Food name |
| `limit` | integer | 5 | Max results (capped at 50) |

**Example:**
```
GET /api/nutrition/search?q=tomato&limit=5
```

---

### `GET /api/nutrition/<fdc_id>`

Return normalized nutrition data for a single USDA food by FDC ID.

**Example:**
```
GET /api/nutrition/321358
```

---

### `GET /api/nutrition`

List all foods available in the local Foundation Foods dataset.

---

### `GET /api/compare`

Compare multiple USDA foods against a single BLS price series, sorted by a chosen metric. Useful for finding the best nutritional value within a food category.

| Param | Type | Default | Description |
|---|---|---|---|
| `series_id` | string | required | BLS AP series ID |
| `fdc_ids` | string | required | Comma-separated list of FDC IDs (max 25) |
| `sort_by` | string | `protein_per_dollar` | Sort metric: `protein_per_dollar`, `calories_per_dollar`, or `fiber_per_dollar` |

**Example:**
```
GET /api/compare?series_id=APU0000706111&fdc_ids=321358,321360&sort_by=protein_per_dollar
```
```json
{
  "series_id": "APU0000706111",
  "bls_item":  "Chicken, fresh, whole, per lb.",
  "bls_area":  "U.S. city average",
  "sort_by":   "protein_per_dollar",
  "comparisons": [ ... ],
  "errors": []
}
```

---

### `GET /api/trend/<series_id>`

Return historical BLS prices for a series with average and current-vs-average comparison.

| Param | Type | Default | Description |
|---|---|---|---|
| `years` | integer | 10 | Number of years of history (max 30) |

**Example:**
```
GET /api/trend/APU0000706111?years=5
```
```json
{
  "series_id":    "APU0000706111",
  "item":         "Chicken, fresh, whole, per lb.",
  "area":         "U.S. city average",
  "unit":         "USD_per_lb",
  "points":       [ { "date": "2014-01", "price": 1.52 }, "..." ],
  "average":      1.61,
  "current":      1.48,
  "current_date": "2018-06",
  "vs_average":   -8.07,
  "year_range":   [2014, 2018]
}
```

---

### `GET /api/suggest-pairing/bls/<series_id>`

Given a BLS series ID, return similar BLS series and candidate USDA foods. Powers swap suggestions on the pairing interface.

```
GET /api/suggest-pairing/bls/APU0000706111?limit=5
```

---

### `GET /api/suggest-pairing/usda/<fdc_id>`

Given a USDA FDC ID, return similar USDA foods and candidate BLS series. Powers swap suggestions on the pairing interface.

```
GET /api/suggest-pairing/usda/321358?limit=5
```

---

### `GET /analytics/top-series`

Return the 5 most-accessed BLS series based on the SQLite access log. Useful for understanding usage patterns and detecting anomalies.

```json
{
  "top_series": [
    { "series_id": "APU0000706111", "item_name": "Chicken, fresh, whole, per lb.", "access_count": 42 }
  ]
}
```

---

### Other Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Health check / welcome message |
| `GET /api/health` | Returns `{ "status": "ok" }` |
| `GET /series` | List all BLS series loaded from local files |
| `GET /data/<series_id>` | Raw BLS price data by year for a series |

---

## Output Structure

Each `/api/pair` response is a JSON object with the following fields:

| Field | Type | Description |
|---|---|---|
| `fdc_id` | string | USDA Foundation Foods identifier |
| `description` | string | Food name from Foundation Foods |
| `basis_amount_g` | integer | Gram basis for all nutrient values (always 100) |
| `nutrients` | object | Nutrient values per 100g — protein, energy, fat, carbs, fiber, sodium — each with `value` and `unit` |
| `bls` | object | BLS price data: series ID, item, area, normalized price (USD/100g), and source price (USD/lb) |
| `derivedMetrics` | object | `protein_per_dollar`, `calories_per_dollar`, and others — each with `value` and `unit` |
| `metadata` | object | Schema version and dataset source URLs |
| `pairingNotes` | object | Match type and any warnings about the food-to-series pairing |

**Example response:**

```json
{
  "fdc_id": "321358",
  "description": "Hummus, commercial",
  "basis_amount_g": 100,
  "nutrients": {
    "protein": { "value": 7.35, "unit": "g" },
    "energy":  { "value": 229,  "unit": "kcal" },
    "fat":     { "value": 17.1, "unit": "g" },
    "carbs":   { "value": 14.9, "unit": "g" },
    "fiber":   { "value": 5.4,  "unit": "g" },
    "sodium":  { "value": 438,  "unit": "mg" }
  },
  "bls": {
    "series_id": "APU0000706111",
    "item":      "Chicken, fresh, whole, per lb.",
    "area":      "U.S. city average",
    "price": {
      "value":        0.354,
      "unit":         "USD_per_100g",
      "source_value": 1.607,
      "source_unit":  "USD_per_lb"
    }
  },
  "derivedMetrics": {
    "protein_per_dollar":  { "value": 20.76, "unit": "g_per_USD" },
    "calories_per_dollar": { "value": 647.2, "unit": "kcal_per_USD" }
  },
  "metadata": {
    "schemaVersion": "1.0.0",
    "datasetInfo": {
      "foundationFoods": { "source": "https://fdc.nal.usda.gov/" },
      "bls":             { "source": "https://download.bls.gov/pub/time.series/ap/" }
    }
  },
  "pairingNotes": {
    "match_type": "manual",
    "warning": null
  }
}
```

> Results are descriptive only. Do not use as dietary or policy guidance.

---

## Quality & Performance

### Security & Monitoring

Access logging is implemented via SQLite (`series_access.db`). Every BLS series lookup is recorded with a timestamp, enabling:
- Detection of unusual access spikes or repeated queries that may indicate scraping or misuse
- Usage analytics to understand which food categories are most queried
- Auditability of data access patterns over time

This maps to the security design described in G7: status tracking and anomaly detection without storing any personal user data.

### Functional Quality

Verified via 97-test pytest suite (`pytest tests/test_suite.py -v`) and live API responses.

| Check | Target | Actual | Status |
|---|---|---|---|
| Unit field presence (value + unit on every nutrient) | 100% | 100% — confirmed in all `/api/pair` responses | Pass |
| 100g basis on all records | 100% | 100% — `basis_amount_g: 100.0` on all records | Pass |
| Price conversion accuracy (USD/lb to USD/100g) | +/-0.001 | Verified: $2.026/lb -> $0.446657/100g (expected $0.44666) | Pass |
| Derived metric accuracy (recomputed vs. stored) | +/-0.01 | Verified: protein 7.35 / 0.446657 = 16.456 (stored 16.4556) | Pass |
| Schema version field present | 100% | 100% — `schemaVersion: "1.0.0"` on all records | Pass |
| Both source datasets load without errors | Pass | Pass — server startup completes cleanly | Pass |
| Output schema validation (jsonschema) | 0 errors | 0 errors on all tested records | Pass |
| Automated test suite | 97 tests passing | 97 passed, 0 failed | Pass |

### Performance

Measured on local machine (Zenbook) with full Foundation Foods + BLS datasets loaded.

| Measure | Target | Actual |
|---|---|---|
| Server startup (load + parse both datasets) | < 30s | ~16s |
| `/api/search` response time | < 2s | 44ms |
| `/api/pair` response time | < 1s | 97ms |
| `/api/trend` response time | < 1s | 75ms |
| `/api/compare` (10 foods) response time | < 5s | 104ms |

### Remediation Notes

- If derived metric accuracy fails: recompute `protein_per_dollar` as `nutrients.protein.value / bls.price.value` and compare to stored value. Mismatch indicates a rounding or order-of-operations issue in `usda_bls_bridge.py`.
- If price conversion fails: verify divisor is 4.536 (453.6g per lb ÷ 100). Check for off-by-10x errors if BLS updates its source unit labeling.
- If BLS files fail to parse: confirm tab-delimiter and expected columns (`series_id`, `year`, `period`, `value`) are present. BLS occasionally reformats headers on new releases.
- If USDA JSON fails to parse: confirm the file is the Foundation Foods bulk format with top-level key `FoundationFoods`.

---

## Known Limitations

- BLS price data reflects historical retail averages and may not match current market prices.
- Food-to-BLS-series matching uses fuzzy name matching and may produce incorrect pairings for ambiguous food names (e.g. "ground beef" matches multiple BLS series). The `pairingNotes.warning` field flags uncertain matches.
- Derived metrics cover protein, calories, and fiber per dollar. Micronutrients and other nutritional dimensions are not included in the cost-efficiency calculation.
- Analysis is limited to U.S. retail prices and does not generalize to other food systems or purchasing contexts.
- Results are descriptive only and should not be used as dietary or policy guidance.
