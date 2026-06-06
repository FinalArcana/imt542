"""
usda_bls_bridge.py
------------------
Loads USDA Foundation Foods from a local JSON file and pairs records
with BLS Average Price data to compute derived nutrition-cost metrics.

Expected local file format (USDA bulk download):
  { "FoundationFoods": [ { ...food record... }, ... ] }

All nutrient values are on a 100-gram basis (Foundation Foods default).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import ValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAMS_PER_LB = 453.592
BASIS_G = 100.0

# Nutrient IDs we care about for derived metrics and display
NUTRIENT_IDS = {
    1003: ("protein",   "g"),
    1008: ("energy",    "kcal"),
    1062: ("energy_kj", "kJ"),
    1004: ("fat",       "g"),
    1005: ("carbs",     "g"),
    1079: ("fiber",     "g"),
    1093: ("sodium",    "mg"),
}

# ---------------------------------------------------------------------------
# Output schema (G7)
# Validates the structure returned by pair_usda_bls before it leaves the API.
# ---------------------------------------------------------------------------

NUTRIENT_VALUE_SCHEMA = {
    "type": "object",
    "required": ["value", "unit"],
    "properties": {
        "value": {"type": "number"},
        "unit":  {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

PAIR_OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "fdc_id", "description", "basis_amount_g",
        "nutrients", "bls", "derivedMetrics", "metadata", "pairingNotes",
    ],
    "properties": {
        "fdc_id":          {"type": "string", "minLength": 1},
        "description":     {"type": "string", "minLength": 1},
        "basis_amount_g":  {"type": "number", "const": 100.0},

        "nutrients": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": NUTRIENT_VALUE_SCHEMA,
        },

        "bls": {
            "type": "object",
            "required": ["series_id", "item", "area", "price"],
            "properties": {
                "series_id": {"type": "string", "minLength": 1},
                "item":      {"type": "string"},
                "area":      {"type": "string"},
                "price": {
                    "oneOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "required": ["value", "unit", "source_value", "source_unit"],
                            "properties": {
                                "value":            {"type": "number", "exclusiveMinimum": 0},
                                "unit":             {"type": "string", "const": "USD_per_100g"},
                                "source_value":     {"type": "number", "exclusiveMinimum": 0},
                                "source_unit":      {"type": "string", "const": "USD_per_lb"},
                                "reference_period": {"type": ["string", "null"]},
                            },
                            "additionalProperties": False,
                        },
                    ]
                },
            },
        },

        "derivedMetrics": {
            "type": "object",
            "additionalProperties": NUTRIENT_VALUE_SCHEMA,
        },

        "metadata": {
            "type": "object",
            "required": ["schemaVersion", "datasetInfo"],
            "properties": {
                "schemaVersion": {"type": "string", "const": "1.0.0"},
                "datasetInfo": {
                    "type": "object",
                    "required": ["foundationFoods", "bls_ap"],
                    "properties": {
                        "foundationFoods": {
                            "type": "object",
                            "required": ["source"],
                            "properties": {"source": {"type": "string"}, "description": {"type": "string"}},
                        },
                        "bls_ap": {
                            "type": "object",
                            "required": ["source"],
                            "properties": {"source": {"type": "string"}, "description": {"type": "string"}},
                        },
                    },
                },
            },
        },

        "pairingNotes": {
            "type": "object",
            "required": ["match_type"],
            "properties": {
                "match_type": {"type": "string"},
                "warning":    {"type": ["string", "null"]},
            },
        },
    },
    "additionalProperties": False,
}


def validate_pair_output(record: dict) -> list[str]:
    """
    Validate a pair_usda_bls output record against PAIR_OUTPUT_SCHEMA.

    Returns a list of validation error messages (empty = valid).
    Raises nothing — callers decide how to handle errors.
    """
    validator = jsonschema.Draft7Validator(PAIR_OUTPUT_SCHEMA)
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    return [f"{' -> '.join(str(p) for p in e.path) or 'root'}: {e.message}" for e in errors]


# ---------------------------------------------------------------------------
# Local USDA data loader
# ---------------------------------------------------------------------------

# Module-level cache: loaded once on first use
_usda_by_fdc_id: dict[str, dict] | None = None
_usda_index: list[dict] | None = None   # lightweight list for search


def _load_usda(path: str | Path) -> None:
    """Parse the local Foundation Foods JSON file into module-level caches."""
    global _usda_by_fdc_id, _usda_index
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"USDA data file not found: {p}")

    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)

    foods: list[dict] = raw.get("FoundationFoods", raw) if isinstance(raw, dict) else raw

    _usda_by_fdc_id = {}
    _usda_index = []
    for food in foods:
        fdc_id = str(food.get("fdcId", ""))
        if fdc_id:
            _usda_by_fdc_id[fdc_id] = food
            _usda_index.append({
                "fdc_id":       fdc_id,
                "description":  food.get("description", ""),
                "foodCategory": (food.get("foodCategory") or {}).get("description", ""),
            })

    print(f"[usda_bls_bridge] Loaded {len(_usda_by_fdc_id)} Foundation Foods records from {p}")


def init_usda(path: str | Path) -> None:
    """Call this once at app startup with the path to your local JSON file."""
    _load_usda(path)


def _require_loaded() -> None:
    if _usda_by_fdc_id is None:
        raise RuntimeError(
            "USDA data not loaded. Call usda_bls_bridge.init_usda(path) at startup."
        )


# ---------------------------------------------------------------------------
# Nutrient extraction
# ---------------------------------------------------------------------------

def _extract_nutrients(food_nutrients: list[dict]) -> dict:
    """
    Pull key nutrient IDs from a FoodNutrients array.
    Returns {name: {value, unit}} on a per-100g basis.
    Foundation Foods already use 100g as the basis — no scaling needed.
    """
    result: dict[str, dict] = {}
    for fn in food_nutrients:
        n = fn.get("nutrient") or {}
        nid = n.get("id")
        if nid in NUTRIENT_IDS:
            label, unit = NUTRIENT_IDS[nid]
            value = fn.get("amount") if fn.get("amount") is not None else fn.get("median")
            if value is not None:
                result[label] = {"value": round(float(value), 4), "unit": unit}
    return result


# ---------------------------------------------------------------------------
# Public lookup / search
# ---------------------------------------------------------------------------

def get_usda_food(fdc_id: int | str) -> dict | None:
    """
    Look up a food by FDC ID from the local dataset.
    Returns a normalised dict, or None if not found.
    """
    _require_loaded()
    record = _usda_by_fdc_id.get(str(fdc_id))
    if record is None:
        return None
    return _normalise_record(record)


def search_usda_foods(query: str, page_size: int = 5) -> list[dict]:
    """
    Case-insensitive substring search over description and food category.
    Returns compact dicts with fdc_id, description, foodCategory.
    """
    _require_loaded()
    q = query.lower()
    results = []
    for item in _usda_index:
        if q in item["description"].lower() or q in item["foodCategory"].lower():
            results.append(item)
            if len(results) >= page_size:
                break
    return results


def list_all_foods() -> list[dict]:
    """Return the full lightweight index (fdc_id, description, foodCategory)."""
    _require_loaded()
    return list(_usda_index)


def _normalise_record(record: dict) -> dict:
    """Convert a raw Foundation Foods record into the normalised shape used by the API."""
    return {
        "ok":           True,
        "fdc_id":       str(record.get("fdcId", "")),
        "description":  record.get("description", ""),
        "foodCategory": (record.get("foodCategory") or {}).get("description", ""),
        "basis_amount_g": BASIS_G,
        "nutrients":    _extract_nutrients(record.get("foodNutrients", [])),
    }


# ---------------------------------------------------------------------------
# BLS price helpers
# ---------------------------------------------------------------------------

def latest_price_from_bls_data(data_by_year: dict) -> tuple[float | None, str | None]:
    """
    Given the data_by_year dict from /data/<series_id>,
    return (price_per_lb, period_label) for the most recent observation.
    """
    if not data_by_year:
        return None, None

    latest_year = max(data_by_year.keys(), key=lambda y: int(y))
    observations = data_by_year[latest_year]

    monthly = [o for o in observations if re.match(r"M\d{2}", o.get("period", ""))]
    pool = monthly if monthly else observations
    if not pool:
        return None, None

    latest_obs = max(pool, key=lambda o: o.get("period", ""))
    try:
        price = float(latest_obs["value"])
        period_label = f"{latest_year}-{latest_obs['period']}"
        return price, period_label
    except (KeyError, ValueError, TypeError):
        return None, None


def price_per_100g(price_per_lb: float) -> float:
    """Convert USD/lb → USD/100g."""
    return round(price_per_lb / GRAMS_PER_LB * BASIS_G, 6)


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

def compute_derived_metrics(nutrients: dict, usd_per_100g: float) -> dict:
    """Compute nutrition-per-dollar metrics matching the G7 schema."""
    metrics: dict[str, dict] = {}
    if usd_per_100g <= 0:
        return metrics

    protein = (nutrients.get("protein") or {}).get("value")
    energy  = (nutrients.get("energy") or {}).get("value")
    fat     = (nutrients.get("fat") or {}).get("value")
    fiber   = (nutrients.get("fiber") or {}).get("value")

    if protein is not None:
        metrics["protein_per_dollar"]  = {"value": round(protein / usd_per_100g, 4), "unit": "g_per_USD"}
    if energy is not None:
        metrics["calories_per_dollar"] = {"value": round(energy  / usd_per_100g, 4), "unit": "kcal_per_USD"}
    if fat is not None:
        metrics["fat_per_dollar"]      = {"value": round(fat     / usd_per_100g, 4), "unit": "g_per_USD"}
    if fiber is not None:
        metrics["fiber_per_dollar"]    = {"value": round(fiber   / usd_per_100g, 4), "unit": "g_per_USD"}
    return metrics


# ---------------------------------------------------------------------------
# Main pairing function
# ---------------------------------------------------------------------------

def pair_usda_bls(
    fdc_id: int | str,
    bls_series_meta: dict,
    bls_data_by_year: dict,
) -> dict:
    """
    Look up local USDA nutrition for fdc_id, pair it with BLS price data,
    and return the integrated G7-schema record.

    The returned dict always includes a top-level "validationErrors" key:
      - empty list  → output passed schema validation
      - non-empty   → list of human-readable error strings describing failures
    Callers can decide whether to surface these as a 500 or include them
    in the response for debugging.
    """
    usda = get_usda_food(fdc_id)
    if usda is None:
        return {"ok": False, "error": f"fdc_id '{fdc_id}' not found in local dataset"}

    price_lb, period = latest_price_from_bls_data(bls_data_by_year)
    price_100g = price_per_100g(price_lb) if price_lb is not None else None
    derived    = compute_derived_metrics(usda["nutrients"], price_100g) if price_100g else {}

    record = {
        "fdc_id":        usda["fdc_id"],
        "description":   usda["description"],
        "basis_amount_g": BASIS_G,
        "nutrients":     usda["nutrients"],

        "bls": {
            "series_id": bls_series_meta.get("series_id"),
            "item":      bls_series_meta.get("item"),
            "area":      bls_series_meta.get("area"),
            "price": {
                "value":              price_100g,
                "unit":               "USD_per_100g",
                "source_value":       price_lb,
                "source_unit":        "USD_per_lb",
                "reference_period":   period,
            } if price_100g is not None else None,
        },

        "derivedMetrics": derived,

        "metadata": {
            "schemaVersion": "1.0.0",
            "datasetInfo": {
                "foundationFoods": {
                    "source": "https://fdc.nal.usda.gov/",
                    "description": "USDA Foundation Foods nutrient composition dataset (local).",
                },
                "bls_ap": {
                    "source": "https://www.bls.gov/cpi/factsheets/average-prices.htm",
                    "description": "BLS Average Retail Food Prices dataset.",
                },
            },
        },

        "pairingNotes": {
            "match_type": "manual",
            "warning": (
                "BLS item categories are broader than individual FDC foods. "
                "Derived metrics are illustrative; validate before drawing "
                "dietary or policy conclusions."
            ),
        },
    }

    record["validationErrors"] = validate_pair_output(record)
    return record


# ---------------------------------------------------------------------------
# Suggest USDA queries for a BLS item name
# ---------------------------------------------------------------------------

BLS_TO_USDA_KEYWORDS: dict[str, str] = {
    "chicken":      "chicken",
    "beef":         "beef",
    "pork":         "pork",
    "eggs":         "egg",
    "milk":         "milk",
    "bread":        "bread",
    "rice":         "rice",
    "beans":        "beans",
    "tuna":         "tuna",
    "orange juice": "orange juice",
    "tomatoes":     "tomato",
    "potatoes":     "potato",
    "lettuce":      "lettuce",
    "apples":       "apple",
    "bananas":      "banana",
    "flour":        "flour",
    "sugar":        "sugar",
    "butter":       "butter",
    "cheese":       "cheese",
    "coffee":       "coffee",
    "watermelon":   "watermelon",
    "hummus":       "hummus",
}


def suggest_search_query_for_item(item_name: str) -> str | None:
    """
    Map a BLS item name to a USDA keyword for local search.
    Returns a search string, or None if no match.
    """
    name_lower = item_name.lower()
    for keyword, query in BLS_TO_USDA_KEYWORDS.items():
        if keyword in name_lower:
            return query
    # Fallback: strip BLS suffixes and use cleaned name
    clean = re.sub(r",?\s*(fresh|frozen|canned|dried|per lb|per dozen)\b.*", "", name_lower).strip()
    return clean or None

# ---------------------------------------------------------------------------
# Token-overlap scoring (used by unified search)
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> set[str]:
    """
    Lowercase, strip punctuation, split on whitespace.
    Drops single-character tokens and common stop words.
    """
    STOPWORDS = {"a", "an", "the", "and", "or", "of", "by", "with", "in",
                 "for", "to", "raw", "cooked", "fresh", "frozen", "dried",
                 "canned", "per", "lb", "oz", "whole", "only"}
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 1 and t not in STOPWORDS}


def score_match(query: str, target: str) -> float:
    """
    Fraction of query tokens found in target tokens.
    Returns 0.0–1.0; 1.0 means every query word appeared in the target.
    Bonus +0.2 (capped at 1.0) if the full query string is a substring.
    """
    q_tokens = _tokenise(query)
    if not q_tokens:
        return 0.0
    t_tokens = _tokenise(target)
    overlap = len(q_tokens & t_tokens) / len(q_tokens)
    bonus = 0.2 if query.lower() in target.lower() else 0.0
    return min(1.0, round(overlap + bonus, 4))


# ---------------------------------------------------------------------------
# Unified search across both datasets
# ---------------------------------------------------------------------------

def search_unified(
    query: str,
    bls_series_index: list[dict],
    limit: int = 10,
    min_score: float = 0.3,
) -> list[dict]:
    """
    Search both USDA and BLS datasets by token-overlap score.

    bls_series_index — list of dicts with at least:
        { series_id, item_name, area_name }
      Pass only city-average rows (area_code == "0000") for clean results.

    Returns a list of result dicts sorted by score descending:
    {
        "label":       display name shown to user,
        "source":      "usda" | "bls",
        "id":          fdc_id  or  series_id,
        "category":    foodCategory or BLS item name,
        "score":       float,
    }
    Only results with score >= min_score are included.
    """
    _require_loaded()
    results: list[dict] = []

    # USDA side
    for item in _usda_index:
        s = max(
            score_match(query, item["description"]),
            score_match(query, item["foodCategory"]),
        )
        if s >= min_score:
            results.append({
                "label":    item["description"],
                "source":   "usda",
                "id":       item["fdc_id"],
                "category": item["foodCategory"],
                "score":    s,
            })

    # BLS side
    for row in bls_series_index:
        s = score_match(query, row["item_name"])
        if s >= min_score:
            results.append({
                "label":    row["item_name"],
                "source":   "bls",
                "id":       row["series_id"],
                "category": row["item_name"],
                "score":    s,
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Suggest similar records (swap affordance for the pairing page)
# ---------------------------------------------------------------------------

def suggest_similar_usda(fdc_id: int | str, limit: int = 5) -> dict:
    """
    Given a USDA fdc_id, return:
      - similar USDA foods in the same foodCategory
      - candidate BLS series matched by keyword from the food's description
    """
    _require_loaded()
    record = _usda_by_fdc_id.get(str(fdc_id))
    if record is None:
        return {"error": f"fdc_id '{fdc_id}' not found"}

    category    = (record.get("foodCategory") or {}).get("description", "")
    description = record.get("description", "")

    # Similar USDA: same category, exclude self
    similar_usda = [
        item for item in _usda_index
        if item["foodCategory"] == category and item["fdc_id"] != str(fdc_id)
    ][:limit]

    # BLS keyword: derive from description using existing map
    bls_keyword = suggest_search_query_for_item(description)

    return {
        "fdc_id":        str(fdc_id),
        "description":   description,
        "foodCategory":  category,
        "similar_usda":  similar_usda,
        "bls_keyword":   bls_keyword,   # app.py uses this to query BLS in-memory
    }


def suggest_similar_bls(
    series_id: str,
    bls_series_index: list[dict],
    full_series_index: list[dict] | None = None,
    limit: int = 5,
) -> dict:
    """
    Given a BLS series_id, return:
      - similar BLS series by token-overlap on item_name (city-average area)
      - candidate USDA foods matched by keyword from the item name

    full_series_index: the complete series list (all areas) used to look up
    the input series_id when it may not be in the city-average-only index.
    Falls back to bls_series_index if not provided.
    """
    _require_loaded()

    # Look up the input series — check full index first so non-city-avg
    # series_ids (which won't be in bls_series_index) are still found.
    lookup = full_series_index if full_series_index else bls_series_index
    match  = next((r for r in lookup if r["series_id"] == series_id), None)
    if match is None:
        return {"error": f"series_id '{series_id}' not found"}

    item_name = match["item_name"]

    # Similar BLS: score all city-average series by token overlap against
    # the input item_name, exclude self, return top N above threshold.
    scored = []
    for r in bls_series_index:
        if r["series_id"] == series_id:
            continue
        s = score_match(item_name, r["item_name"])
        if s >= 0.4:
            scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    similar_bls = [
        {
            "series_id": r["series_id"],
            "item_name": r["item_name"],
            "area_name": r["area_name"],
            "score":     round(s, 3),
        }
        for s, r in scored[:limit]
    ]

    # USDA candidates: keyword search from item name
    usda_keyword    = suggest_search_query_for_item(item_name)
    usda_candidates = search_usda_foods(usda_keyword, page_size=limit) if usda_keyword else []

    return {
        "series_id":       series_id,
        "item_name":       item_name,
        "similar_bls":     similar_bls,
        "usda_candidates": usda_candidates,
        "usda_keyword":    usda_keyword,
    }


# ---------------------------------------------------------------------------
# Price trend  (last N years, monthly, with average + current annotation)
# ---------------------------------------------------------------------------

def price_trend(
    data_by_year: dict,
    years: int = 10,
) -> dict:
    """
    Build a price trend payload for the last `years` years of BLS monthly data.

    Returns:
    {
      "points":  [ {"date": "YYYY-MM", "price": float}, ... ],   # chronological
      "average": float,          # mean of all points in window
      "current": float | None,   # most recent price
      "current_date": str,       # e.g. "2018-M06"
      "vs_average": float,       # (current - average) / average * 100  (% diff)
      "year_range": [min_year, max_year],
    }
    """
    if not data_by_year:
        return {}

    all_years = sorted(data_by_year.keys(), key=lambda y: int(y))
    cutoff    = int(all_years[-1]) - years + 1

    points: list[dict] = []
    for year_key in all_years:
        if int(year_key) < cutoff:
            continue
        for obs in data_by_year[year_key]:
            period = obs.get("period", "")
            # Keep only monthly observations (M01–M12)
            if not re.match(r"M(0[1-9]|1[0-2])$", period):
                continue
            try:
                price = float(obs["value"])
            except (KeyError, ValueError, TypeError):
                continue
            month_num = period[1:]   # "M06" -> "06"
            points.append({
                "date":  f"{year_key}-{month_num}",
                "price": round(price, 4),
            })

    if not points:
        return {}

    # Sort chronologically
    points.sort(key=lambda p: p["date"])

    prices  = [p["price"] for p in points]
    average = round(sum(prices) / len(prices), 4)
    current = points[-1]["price"]
    current_date = points[-1]["date"]
    vs_avg  = round((current - average) / average * 100, 2) if average else None

    return {
        "points":       points,
        "average":      average,
        "current":      current,
        "current_date": current_date,
        "vs_average":   vs_avg,   # positive = more expensive than avg, negative = cheaper
        "year_range":   [int(points[0]["date"][:4]), int(points[-1]["date"][:4])],
    }
