import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pandas as pd

import usda_bls_bridge as usda
from validators import (
    validate_series_id,
    validate_fdc_id,
    validate_fdc_ids_list,
    validate_years,
    validate_sort_by,
)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Rate limiter — generous defaults for prototype; tighten per-endpoint as needed.
limiter = Limiter(
    key_func       = get_remote_address,
    app            = app,
    default_limits = [],        # no global limit; applied per-route only
    storage_uri    = "memory://",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "series_access.db"

# Path to the local USDA Foundation Foods JSON file.
# Expects the USDA bulk-download format: { "FoundationFoods": [...] }
USDA_DATA_PATH = BASE_DIR / "data" / "FoodData_Central_foundation_food_json_2025-12-18.json"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT NOT NULL,
                accessed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def record_series_access(series_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO series_access_log (series_id) VALUES (?)",
            (series_id,),
        )
        conn.commit()


def get_top_accessed_series(limit=5):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT series_id, COUNT(*) AS access_count
            FROM series_access_log
            GROUP BY series_id
            ORDER BY access_count DESC, series_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    item_name_lookup = series.set_index("series_id")["item_name"].to_dict()
    return [
        {
            "series_id":    sid,
            "access_count": cnt,
            "item_name":    item_name_lookup.get(sid),
        }
        for sid, cnt in rows
    ]


# ---------------------------------------------------------------------------
# Load BLS data
# ---------------------------------------------------------------------------

def clean_df(df):
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    return df


series = pd.read_csv("data/ap.series",      sep="\t")
data   = pd.read_csv("data/ap.data.3.Food", sep="\t")
items  = pd.read_csv("data/ap.item",        sep="\t")
areas  = pd.read_csv("data/ap.area",        sep="\t")

series = clean_df(series)
data   = clean_df(data)
items  = clean_df(items)
areas  = clean_df(areas)

series = series.merge(items, on="item_code").merge(areas, on="area_code")

print(f"Loaded {len(series)} BLS series and {len(data)} data points")

# ---------------------------------------------------------------------------
# Load USDA Foundation Foods (local file)
# ---------------------------------------------------------------------------

usda.init_usda(USDA_DATA_PATH)

# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

init_db()


# ---------------------------------------------------------------------------
# BLS helpers (shared by multiple endpoints)
# ---------------------------------------------------------------------------

# City-average rows only (area_code "0000").
_city_avg = series[series["area_code"] == "0000"]
BLS_CITY_AVG_INDEX: list[dict] = _city_avg[
    ["series_id", "item_name", "area_name"]
].to_dict(orient="records")

# Full series index (all areas)
BLS_FULL_INDEX: list[dict] = series[
    ["series_id", "item_name", "area_name"]
].to_dict(orient="records")

def _series_meta_for(series_id: str) -> dict | None:
    meta = series[series["series_id"] == series_id]
    if meta.empty:
        return None
    return {
        "series_id": series_id,
        "item":      meta.iloc[0]["item_name"],
        "area":      meta.iloc[0]["area_name"],
        "currency":  "USD",
    }


def _data_by_year_for(series_id: str) -> dict | None:
    subset = data[data["series_id"] == series_id]
    if subset.empty:
        return None
    return (
        subset
        .groupby("year")
        .apply(
            lambda g: g[["period", "value"]].to_dict(orient="records"),
            include_groups=False,
        )
        .to_dict()
    )


# ---------------------------------------------------------------------------
# Original BLS endpoints
# ---------------------------------------------------------------------------

@app.route("/series")
def get_series():
    return jsonify(series.to_dict(orient="records"))


@app.route("/data/<series_id>")
def get_series_data(series_id):
    series_id = series_id.upper().strip()

    err = validate_series_id(series_id)
    if err:
        return jsonify({"error": err}), 422

    record_series_access(series_id)

    meta = _series_meta_for(series_id)
    if meta is None:
        return jsonify({"error": "Series not found"}), 404

    dby = _data_by_year_for(series_id)
    if dby is None:
        return jsonify({"error": "No data for this series"}), 404

    return jsonify({**meta, "data_by_year": dby})


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Welcome to the i7 Flask API server"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/analytics/top-series", methods=["GET"])
def top_series():
    return jsonify({"top_series": get_top_accessed_series(5)})


@app.route("/api/greet", methods=["GET"])
def greet():
    name = request.args.get("name", "world")
    return jsonify({"greeting": f"Hello, {name}!"})


@app.route("/api/echo", methods=["POST"])
def echo():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Invalid JSON payload"}), 400
    return jsonify({"echo": body})


# ---------------------------------------------------------------------------
# USDA endpoints
# ---------------------------------------------------------------------------

@app.route("/api/nutrition/<fdc_id>", methods=["GET"])
def get_nutrition(fdc_id):
    err = validate_fdc_id(fdc_id)
    if err:
        return jsonify({"error": err}), 422

    result = usda.get_usda_food(fdc_id)
    if result is None:
        return jsonify({"error": f"fdc_id '{fdc_id}' not found in local dataset"}), 404
    return jsonify(result)


@app.route("/api/nutrition/search", methods=["GET"])
def search_nutrition():
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 5)), 50)

    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    results = usda.search_usda_foods(query, page_size=limit)
    return jsonify({"query": query, "count": len(results), "results": results})


@app.route("/api/nutrition", methods=["GET"])
def list_nutrition():
    return jsonify({"foods": usda.list_all_foods()})


# ---------------------------------------------------------------------------
# Pairing endpoint  (core of the project)
# ---------------------------------------------------------------------------

@app.route("/api/pair", methods=["GET"])
def pair_nutrition_price():
    """
    Pair a local USDA food with BLS price data and return an integrated
    record with derived metrics (protein/dollar, kcal/dollar, etc.).

    Required params:
      series_id  — BLS AP series ID  e.g. APU0000706111
      fdc_id     — USDA FDC food ID  e.g. 321358

    Returns 400 if required params are missing.
    Returns 422 if params are present but semantically invalid.
    Returns 404 if valid params don't match any records.
    Returns 500 if the output fails schema validation (structural bug).
    """
    series_id = request.args.get("series_id", "").upper().strip()
    fdc_id    = request.args.get("fdc_id", "").strip()

    # 400 — missing params
    if not series_id or not fdc_id:
        return jsonify({
            "error": "Both 'series_id' and 'fdc_id' query parameters are required.",
            "example": "/api/pair?series_id=APU0000706111&fdc_id=321358",
        }), 400

    # 422 — params present but semantically invalid
    series_err = validate_series_id(series_id)
    if series_err:
        return jsonify({"error": series_err}), 422

    fdc_err = validate_fdc_id(fdc_id)
    if fdc_err:
        return jsonify({"error": fdc_err}), 422

    # 404 — valid format but not found in data
    bls_meta = _series_meta_for(series_id)
    if bls_meta is None:
        return jsonify({"error": f"BLS series '{series_id}' not found"}), 404

    bls_dby = _data_by_year_for(series_id)
    if bls_dby is None:
        return jsonify({"error": f"No BLS data for series '{series_id}'"}), 404

    record_series_access(series_id)

    result = usda.pair_usda_bls(
        fdc_id           = fdc_id,
        bls_series_meta  = bls_meta,
        bls_data_by_year = bls_dby,
    )

    if not result.get("ok", True) and result.get("error"):
        return jsonify({"error": result["error"]}), 404

    # 500 — output failed schema validation (structural/pipeline bug)
    validation_errors = result.pop("validationErrors", [])
    if validation_errors:
        app.logger.error(
            "Schema validation failed for fdc_id=%s series_id=%s: %s",
            fdc_id, series_id, validation_errors,
        )
        return jsonify({
            "error": "Output failed schema validation. This is a server-side issue.",
            "details": validation_errors,
        }), 500

    return jsonify(result)


# ---------------------------------------------------------------------------
# Unified search across both datasets
# ---------------------------------------------------------------------------

@app.route("/api/search", methods=["GET"])
@limiter.limit("600 per minute")
def unified_search():
    query     = request.args.get("q", "").strip()
    limit     = min(int(request.args.get("limit", 10)), 50)
    min_score = float(request.args.get("min_score", 0.3))

    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    results = usda.search_unified(
        query            = query,
        bls_series_index = BLS_CITY_AVG_INDEX,
        limit            = limit,
        min_score        = min_score,
    )

    return jsonify({"query": query, "count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Suggest-pairing: BLS -> USDA
# ---------------------------------------------------------------------------

@app.route("/api/suggest-pairing/bls/<series_id>", methods=["GET"])
def suggest_pairing_bls(series_id):
    series_id = series_id.upper().strip()
    limit     = min(int(request.args.get("limit", 5)), 20)

    err = validate_series_id(series_id)
    if err:
        return jsonify({"error": err}), 422

    result = usda.suggest_similar_bls(
        series_id          = series_id,
        bls_series_index   = BLS_CITY_AVG_INDEX,
        full_series_index  = BLS_FULL_INDEX,
        limit              = limit,
    )

    if result.get("error"):
        return jsonify({"error": result["error"]}), 404

    return jsonify(result)


# ---------------------------------------------------------------------------
# Suggest-pairing: USDA -> BLS
# ---------------------------------------------------------------------------

@app.route("/api/suggest-pairing/usda/<fdc_id>", methods=["GET"])
def suggest_pairing_usda(fdc_id):
    limit = min(int(request.args.get("limit", 5)), 20)

    err = validate_fdc_id(fdc_id)
    if err:
        return jsonify({"error": err}), 422

    result = usda.suggest_similar_usda(fdc_id=fdc_id, limit=limit)

    if result.get("error"):
        return jsonify({"error": result["error"]}), 404

    bls_keyword    = result.pop("bls_keyword", None)
    bls_candidates: list[dict] = []
    if bls_keyword:
        q = bls_keyword.lower()
        bls_candidates = [
            {"series_id": r["series_id"], "item_name": r["item_name"], "area_name": r["area_name"]}
            for r in BLS_CITY_AVG_INDEX
            if q in r["item_name"].lower()
        ][:limit]

    result["bls_candidates"] = bls_candidates
    return jsonify(result)


# ---------------------------------------------------------------------------
# Multi-food comparison across a single BLS price series
# ---------------------------------------------------------------------------

@app.route("/api/compare", methods=["GET"])
def compare_foods():
    series_id   = request.args.get("series_id", "").upper().strip()
    fdc_ids_raw = request.args.get("fdc_ids", "")
    sort_by     = request.args.get("sort_by", "protein_per_dollar")

    # 400 — missing params
    if not series_id or not fdc_ids_raw:
        return jsonify({
            "error": "Both 'series_id' and 'fdc_ids' (comma-separated) are required.",
            "example": "/api/compare?series_id=APU0000706111&fdc_ids=321358,321360",
        }), 400

    # 422 — series_id format invalid
    series_err = validate_series_id(series_id)
    if series_err:
        return jsonify({"error": series_err}), 422

    # 422 — fdc_ids list invalid
    fdc_ids, fdc_err = validate_fdc_ids_list(fdc_ids_raw)
    if fdc_err:
        return jsonify({"error": fdc_err}), 422

    # 422 — invalid sort_by value
    sort_err = validate_sort_by(sort_by)
    if sort_err:
        return jsonify({"error": sort_err}), 422

    bls_meta = _series_meta_for(series_id)
    if bls_meta is None:
        return jsonify({"error": f"BLS series '{series_id}' not found"}), 404

    bls_dby = _data_by_year_for(series_id)
    if bls_dby is None:
        return jsonify({"error": f"No BLS data for series '{series_id}'"}), 404

    record_series_access(series_id)

    results = []
    errors  = []
    for fdc_id in fdc_ids:
        rec = usda.pair_usda_bls(
            fdc_id           = fdc_id,
            bls_series_meta  = bls_meta,
            bls_data_by_year = bls_dby,
        )
        if not rec.get("ok", True) and rec.get("error"):
            errors.append({"fdc_id": fdc_id, "error": rec["error"]})
            continue

        rec.pop("validationErrors", None)  # strip internal field from compare results

        sort_val = (rec.get("derivedMetrics") or {}).get(sort_by, {})
        results.append({
            "fdc_id":         rec.get("fdc_id"),
            "description":    rec.get("description"),
            "nutrients":      rec.get("nutrients"),
            "price":          (rec.get("bls") or {}).get("price"),
            "derivedMetrics": rec.get("derivedMetrics"),
            "_sort_value":    sort_val.get("value") if isinstance(sort_val, dict) else None,
        })

    results.sort(
        key=lambda r: r.pop("_sort_value") or -1,
        reverse=True,
    )

    return jsonify({
        "series_id":   series_id,
        "bls_item":    bls_meta["item"],
        "bls_area":    bls_meta["area"],
        "sort_by":     sort_by,
        "comparisons": results,
        "errors":      errors,
    })


# ---------------------------------------------------------------------------
# Price trend endpoint
# ---------------------------------------------------------------------------

@app.route("/api/trend/<series_id>", methods=["GET"])
def price_trend(series_id):
    series_id = series_id.upper().strip()

    err = validate_series_id(series_id)
    if err:
        return jsonify({"error": err}), 422

    years_raw = request.args.get("years", "10")
    years, years_err = validate_years(years_raw)
    if years_err:
        return jsonify({"error": years_err}), 422

    meta = _series_meta_for(series_id)
    if meta is None:
        return jsonify({"error": f"BLS series '{series_id}' not found"}), 404

    dby = _data_by_year_for(series_id)
    if dby is None:
        return jsonify({"error": f"No price data for series '{series_id}'"}), 404

    trend = usda.price_trend(dby, years=years)
    if not trend:
        return jsonify({"error": "Not enough data to build trend"}), 404

    return jsonify({
        "series_id":    series_id,
        "item":         meta["item"],
        "area":         meta["area"],
        "unit":         "USD_per_lb",
        **trend,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
