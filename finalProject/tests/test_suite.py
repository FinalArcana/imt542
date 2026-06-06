"""
tests/test_suite.py
-------------------
Pytest test suite for the Nutrition-Cost Finder.

Covers:
  - validators.py       — all input validation functions
  - usda_bls_bridge.py  — price conversion, derived metrics, pairing,
                          output schema validation, search, trend
                          
No real data files required — all USDA and BLS data is provided via fixtures.
Run with: pytest tests/test_suite.py -v
"""

import pytest
import sys
import os

# Allow imports from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validators import (
    validate_series_id,
    validate_fdc_id,
    validate_fdc_ids_list,
    validate_years,
    validate_sort_by,
    VALID_SORT_FIELDS,
)
import usda_bls_bridge as usda


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def load_usda_fixture(tmp_path):
    """
    Load a minimal synthetic Foundation Foods dataset before each test.
    Uses tmp_path so tests are fully isolated from any real data files.
    """
    import json

    foods = {
        "FoundationFoods": [
            {
                "fdcId": 100001,
                "description": "Chicken breast, raw",
                "foodCategory": {"description": "Poultry Products"},
                "foodNutrients": [
                    {"nutrient": {"id": 1003}, "amount": 21.2},   # protein
                    {"nutrient": {"id": 1008}, "amount": 165.0},  # energy kcal
                    {"nutrient": {"id": 1004}, "amount": 3.6},    # fat
                    {"nutrient": {"id": 1005}, "amount": 0.0},    # carbs
                    {"nutrient": {"id": 1079}, "amount": 0.0},    # fiber
                    {"nutrient": {"id": 1093}, "amount": 74.0},   # sodium
                ],
            },
            {
                "fdcId": 100002,
                "description": "Hummus, commercial",
                "foodCategory": {"description": "Legumes and Legume Products"},
                "foodNutrients": [
                    {"nutrient": {"id": 1003}, "amount": 7.35},
                    {"nutrient": {"id": 1008}, "amount": 229.0},
                    {"nutrient": {"id": 1004}, "amount": 17.1},
                    {"nutrient": {"id": 1005}, "amount": 14.9},
                    {"nutrient": {"id": 1079}, "amount": 5.4},
                    {"nutrient": {"id": 1093}, "amount": 438.0},
                ],
            },
            {
                "fdcId": 100003,
                "description": "Chicken thigh, raw",
                "foodCategory": {"description": "Poultry Products"},
                "foodNutrients": [
                    {"nutrient": {"id": 1003}, "amount": 18.0},
                    {"nutrient": {"id": 1008}, "amount": 200.0},
                    {"nutrient": {"id": 1004}, "amount": 10.0},
                ],
            },
        ]
    }

    data_file = tmp_path / "foundation_foods.json"
    data_file.write_text(json.dumps(foods), encoding="utf-8")
    usda.init_usda(data_file)
    yield


@pytest.fixture
def bls_meta():
    return {
        "series_id": "APU0000706111",
        "item":      "Chicken, fresh, whole, per lb.",
        "area":      "U.S. city average",
        "currency":  "USD",
    }


@pytest.fixture
def bls_data_by_year():
    """Synthetic BLS price data — two years, monthly observations."""
    return {
        "2017": [
            {"period": "M01", "value": "1.45"},
            {"period": "M06", "value": "1.50"},
            {"period": "M12", "value": "1.55"},
        ],
        "2018": [
            {"period": "M01", "value": "1.60"},
            {"period": "M06", "value": "1.65"},
            {"period": "M12", "value": "1.70"},
        ],
    }


@pytest.fixture
def paired_record(bls_meta, bls_data_by_year):
    """A fully paired record for reuse across schema/metric tests."""
    return usda.pair_usda_bls(
        fdc_id           = "100001",
        bls_series_meta  = bls_meta,
        bls_data_by_year = bls_data_by_year,
    )


# ===========================================================================
# validators.py — validate_series_id
# ===========================================================================

class TestValidateSeriesId:
    def test_valid_city_average(self):
        assert validate_series_id("APU0000706111") is None

    def test_valid_regional(self):
        assert validate_series_id("APU0100706111") is None

    def test_lowercase_rejected(self):
        assert validate_series_id("apu0000706111") is not None

    def test_missing_apu_prefix(self):
        assert validate_series_id("BLS0000706111") is not None

    def test_empty_string(self):
        assert validate_series_id("") is not None

    def test_special_characters(self):
        assert validate_series_id("APU000-70611") is not None

    def test_just_apu(self):
        # "APU" alone is not a valid series ID — requires at least one char after APU
        assert validate_series_id("APU") is not None

    def test_error_message_is_helpful(self):
        err = validate_series_id("bad_id")
        assert "APU" in err
        assert "bad_id" in err


# ===========================================================================
# validators.py — validate_fdc_id
# ===========================================================================

class TestValidateFdcId:
    def test_valid_numeric(self):
        assert validate_fdc_id("321358") is None

    def test_valid_short(self):
        assert validate_fdc_id("1") is None

    def test_alpha_rejected(self):
        assert validate_fdc_id("abc") is not None

    def test_alphanumeric_rejected(self):
        assert validate_fdc_id("321abc") is not None

    def test_empty_string(self):
        assert validate_fdc_id("") is not None

    def test_negative_rejected(self):
        # Negative sign makes it non-digit
        assert validate_fdc_id("-1") is not None

    def test_float_rejected(self):
        assert validate_fdc_id("3.14") is not None

    def test_error_message_contains_id(self):
        err = validate_fdc_id("notanid")
        assert "notanid" in err


# ===========================================================================
# validators.py — validate_fdc_ids_list
# ===========================================================================

class TestValidateFdcIdsList:
    def test_single_valid(self):
        ids, err = validate_fdc_ids_list("321358")
        assert err is None
        assert ids == ["321358"]

    def test_multiple_valid(self):
        ids, err = validate_fdc_ids_list("100001,100002,100003")
        assert err is None
        assert len(ids) == 3

    def test_strips_whitespace(self):
        ids, err = validate_fdc_ids_list("100001, 100002 , 100003")
        assert err is None
        assert ids == ["100001", "100002", "100003"]

    def test_empty_string(self):
        ids, err = validate_fdc_ids_list("")
        assert err is not None
        assert ids == []

    def test_over_limit(self):
        raw = ",".join(str(i) for i in range(26))
        ids, err = validate_fdc_ids_list(raw)
        assert err is not None
        assert "25" in err

    def test_exactly_25_valid(self):
        raw = ",".join(str(i) for i in range(25))
        ids, err = validate_fdc_ids_list(raw)
        assert err is None
        assert len(ids) == 25

    def test_non_numeric_in_list(self):
        ids, err = validate_fdc_ids_list("100001,abc,100003")
        assert err is not None
        assert "abc" in err

    def test_mixed_invalid(self):
        ids, err = validate_fdc_ids_list("100001,bad,also-bad")
        assert err is not None


# ===========================================================================
# validators.py — validate_years
# ===========================================================================

class TestValidateYears:
    def test_valid_default(self):
        val, err = validate_years("10")
        assert err is None
        assert val == 10

    def test_valid_boundary_low(self):
        val, err = validate_years("1")
        assert err is None
        assert val == 1

    def test_valid_boundary_high(self):
        val, err = validate_years("30")
        assert err is None
        assert val == 30

    def test_zero_rejected(self):
        val, err = validate_years("0")
        assert err is not None
        assert val is None

    def test_negative_rejected(self):
        val, err = validate_years("-5")
        assert err is not None

    def test_over_30_rejected(self):
        val, err = validate_years("31")
        assert err is not None
        assert "30" in err

    def test_non_integer_rejected(self):
        val, err = validate_years("abc")
        assert err is not None
        assert val is None

    def test_float_rejected(self):
        val, err = validate_years("5.5")
        assert err is not None


# ===========================================================================
# validators.py — validate_sort_by
# ===========================================================================

class TestValidateSortBy:
    def test_all_valid_fields(self):
        for field in VALID_SORT_FIELDS:
            assert validate_sort_by(field) is None

    def test_invalid_field(self):
        assert validate_sort_by("invalid_metric") is not None

    def test_empty_string(self):
        assert validate_sort_by("") is not None

    def test_error_message_lists_options(self):
        err = validate_sort_by("bad")
        for field in VALID_SORT_FIELDS:
            assert field in err


# ===========================================================================
# usda_bls_bridge — price conversion
# ===========================================================================

class TestPriceConversion:
    def test_known_value(self):
        # $2.93/lb → $0.6459.../100g
        result = usda.price_per_100g(2.93)
        assert abs(result - 0.6459) < 0.001

    def test_one_dollar_per_lb(self):
        result = usda.price_per_100g(1.0)
        expected = 100 / 453.592
        assert abs(result - expected) < 0.0001

    def test_zero(self):
        assert usda.price_per_100g(0.0) == 0.0

    def test_returns_float(self):
        assert isinstance(usda.price_per_100g(1.5), float)


# ===========================================================================
# usda_bls_bridge — latest_price_from_bls_data
# ===========================================================================

class TestLatestPrice:
    def test_picks_most_recent_year(self, bls_data_by_year):
        price, period = usda.latest_price_from_bls_data(bls_data_by_year)
        assert price == 1.70
        assert "2018" in period

    def test_picks_latest_month_in_year(self, bls_data_by_year):
        price, period = usda.latest_price_from_bls_data(bls_data_by_year)
        assert "M12" in period

    def test_empty_dict_returns_none(self):
        price, period = usda.latest_price_from_bls_data({})
        assert price is None
        assert period is None

    def test_single_observation(self):
        data = {"2018": [{"period": "M06", "value": "2.50"}]}
        price, period = usda.latest_price_from_bls_data(data)
        assert price == 2.50

    def test_invalid_value_returns_none(self):
        data = {"2018": [{"period": "M06", "value": "N/A"}]}
        price, period = usda.latest_price_from_bls_data(data)
        assert price is None


# ===========================================================================
# usda_bls_bridge — compute_derived_metrics
# ===========================================================================

class TestDerivedMetrics:
    def test_protein_per_dollar(self):
        nutrients = {"protein": {"value": 21.2, "unit": "g"}}
        price = usda.price_per_100g(2.93)
        metrics = usda.compute_derived_metrics(nutrients, price)
        assert "protein_per_dollar" in metrics
        expected = 21.2 / price
        assert abs(metrics["protein_per_dollar"]["value"] - expected) < 0.01

    def test_calories_per_dollar(self):
        nutrients = {"energy": {"value": 165.0, "unit": "kcal"}}
        price = usda.price_per_100g(2.93)
        metrics = usda.compute_derived_metrics(nutrients, price)
        assert "calories_per_dollar" in metrics
        expected = 165.0 / price
        assert abs(metrics["calories_per_dollar"]["value"] - expected) < 0.01

    def test_units_are_correct(self):
        nutrients = {
            "protein": {"value": 21.2, "unit": "g"},
            "energy":  {"value": 165.0, "unit": "kcal"},
            "fat":     {"value": 3.6, "unit": "g"},
            "fiber":   {"value": 0.0, "unit": "g"},
        }
        metrics = usda.compute_derived_metrics(nutrients, 0.5)
        assert metrics["protein_per_dollar"]["unit"] == "g_per_USD"
        assert metrics["calories_per_dollar"]["unit"] == "kcal_per_USD"
        assert metrics["fat_per_dollar"]["unit"] == "g_per_USD"

    def test_zero_price_returns_empty(self):
        nutrients = {"protein": {"value": 21.2, "unit": "g"}}
        metrics = usda.compute_derived_metrics(nutrients, 0.0)
        assert metrics == {}

    def test_negative_price_returns_empty(self):
        nutrients = {"protein": {"value": 21.2, "unit": "g"}}
        metrics = usda.compute_derived_metrics(nutrients, -1.0)
        assert metrics == {}

    def test_missing_nutrient_skipped(self):
        # Only protein — no energy or fiber in input
        nutrients = {"protein": {"value": 21.2, "unit": "g"}}
        metrics = usda.compute_derived_metrics(nutrients, 0.5)
        assert "protein_per_dollar" in metrics
        assert "calories_per_dollar" not in metrics
        assert "fiber_per_dollar" not in metrics


# ===========================================================================
# usda_bls_bridge — get_usda_food / search
# ===========================================================================

class TestUsdaLookup:
    def test_lookup_known_id(self):
        result = usda.get_usda_food("100001")
        assert result is not None
        assert result["description"] == "Chicken breast, raw"

    def test_lookup_unknown_id(self):
        assert usda.get_usda_food("999999") is None

    def test_lookup_returns_nutrients(self):
        result = usda.get_usda_food("100001")
        assert "protein" in result["nutrients"]
        assert result["nutrients"]["protein"]["value"] == 21.2
        assert result["nutrients"]["protein"]["unit"] == "g"

    def test_lookup_basis_amount(self):
        result = usda.get_usda_food("100001")
        assert result["basis_amount_g"] == 100.0

    def test_search_substring_match(self):
        results = usda.search_usda_foods("chicken")
        assert len(results) >= 1
        assert any("Chicken" in r["description"] for r in results)

    def test_search_case_insensitive(self):
        results_lower = usda.search_usda_foods("chicken")
        results_upper = usda.search_usda_foods("CHICKEN")
        assert len(results_lower) == len(results_upper)

    def test_search_no_match(self):
        results = usda.search_usda_foods("zzznomatch")
        assert results == []

    def test_search_respects_limit(self):
        results = usda.search_usda_foods("chicken", page_size=1)
        assert len(results) <= 1

    def test_list_all_returns_all(self):
        all_foods = usda.list_all_foods()
        assert len(all_foods) == 3


# ===========================================================================
# usda_bls_bridge — pair_usda_bls
# ===========================================================================

class TestPairUsdaBls:
    def test_returns_expected_fields(self, paired_record):
        for field in ("fdc_id", "description", "basis_amount_g",
                      "nutrients", "bls", "derivedMetrics", "metadata", "pairingNotes"):
            assert field in paired_record, f"Missing field: {field}"

    def test_fdc_id_is_string(self, paired_record):
        assert isinstance(paired_record["fdc_id"], str)

    def test_basis_amount_is_100(self, paired_record):
        assert paired_record["basis_amount_g"] == 100.0

    def test_price_unit_is_correct(self, paired_record):
        assert paired_record["bls"]["price"]["unit"] == "USD_per_100g"

    def test_price_source_unit_is_correct(self, paired_record):
        assert paired_record["bls"]["price"]["source_unit"] == "USD_per_lb"

    def test_price_value_positive(self, paired_record):
        assert paired_record["bls"]["price"]["value"] > 0

    def test_derived_metrics_present(self, paired_record):
        assert "protein_per_dollar" in paired_record["derivedMetrics"]
        assert "calories_per_dollar" in paired_record["derivedMetrics"]

    def test_derived_metric_values_non_negative(self, paired_record):
        for key, metric in paired_record["derivedMetrics"].items():
            assert metric["value"] >= 0, f"{key} should be non-negative"

    def test_protein_per_dollar_accuracy(self, paired_record):
        protein = paired_record["nutrients"]["protein"]["value"]
        price   = paired_record["bls"]["price"]["value"]
        stored  = paired_record["derivedMetrics"]["protein_per_dollar"]["value"]
        assert abs(stored - protein / price) < 0.01

    def test_calories_per_dollar_accuracy(self, paired_record):
        energy = paired_record["nutrients"]["energy"]["value"]
        price  = paired_record["bls"]["price"]["value"]
        stored = paired_record["derivedMetrics"]["calories_per_dollar"]["value"]
        assert abs(stored - energy / price) < 0.01

    def test_schema_version(self, paired_record):
        assert paired_record["metadata"]["schemaVersion"] == "1.0.0"

    def test_unknown_fdc_id_returns_error(self, bls_meta, bls_data_by_year):
        result = usda.pair_usda_bls("999999", bls_meta, bls_data_by_year)
        assert result.get("ok") is False
        assert "error" in result

    def test_empty_bls_data_produces_null_price(self, bls_meta):
        result = usda.pair_usda_bls("100001", bls_meta, {})
        assert result["bls"]["price"] is None
        assert result["derivedMetrics"] == {}

    def test_passes_schema_validation(self, paired_record):
        errors = paired_record.get("validationErrors", [])
        assert errors == [], f"Schema validation failed: {errors}"


# ===========================================================================
# usda_bls_bridge — validate_pair_output
# ===========================================================================

class TestValidatePairOutput:
    def test_valid_record_passes(self, paired_record):
        paired_record.pop("validationErrors", None)
        errors = usda.validate_pair_output(paired_record)
        assert errors == []

    def test_missing_fdc_id_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        del paired_record["fdc_id"]
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_wrong_basis_amount_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        paired_record["basis_amount_g"] = 50.0
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_wrong_schema_version_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        paired_record["metadata"]["schemaVersion"] = "2.0.0"
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_wrong_price_unit_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        paired_record["bls"]["price"]["unit"] = "USD_per_lb"
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_nutrient_missing_unit_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        del paired_record["nutrients"]["protein"]["unit"]
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_negative_price_fails(self, paired_record):
        paired_record.pop("validationErrors", None)
        paired_record["bls"]["price"]["value"] = -1.0
        errors = usda.validate_pair_output(paired_record)
        assert len(errors) > 0

    def test_null_price_passes(self, bls_meta):
        # Price can be null when no BLS data is available
        result = usda.pair_usda_bls("100001", bls_meta, {})
        result.pop("validationErrors", None)
        errors = usda.validate_pair_output(result)
        assert errors == []


# ===========================================================================
# usda_bls_bridge — price_trend
# ===========================================================================

class TestPriceTrend:
    def test_returns_expected_keys(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        for key in ("points", "average", "current", "current_date", "vs_average", "year_range"):
            assert key in trend, f"Missing key: {key}"

    def test_points_are_sorted_chronologically(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        dates = [p["date"] for p in trend["points"]]
        assert dates == sorted(dates)

    def test_current_is_most_recent_price(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        assert trend["current"] == 1.70
        assert "2018" in trend["current_date"]

    def test_average_is_within_range(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        prices = [p["price"] for p in trend["points"]]
        assert min(prices) <= trend["average"] <= max(prices)

    def test_vs_average_sign(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        # Current (1.70) is above average of all points, so vs_average should be positive
        assert trend["vs_average"] > 0

    def test_year_range(self, bls_data_by_year):
        trend = usda.price_trend(bls_data_by_year, years=10)
        assert trend["year_range"][0] <= trend["year_range"][1]

    def test_years_parameter_limits_window(self, bls_data_by_year):
        trend_1yr  = usda.price_trend(bls_data_by_year, years=1)
        trend_10yr = usda.price_trend(bls_data_by_year, years=10)
        assert len(trend_1yr["points"]) <= len(trend_10yr["points"])

    def test_empty_data_returns_empty(self):
        trend = usda.price_trend({})
        assert trend == {}

    def test_annual_observations_excluded(self):
        # Annual observations use period "M13" or "S01/S02" — should be filtered
        data = {
            "2018": [
                {"period": "M06", "value": "1.50"},
                {"period": "M13", "value": "1.55"},  # annual average — should be excluded
            ]
        }
        trend = usda.price_trend(data, years=5)
        assert all("M13" not in p["date"] for p in trend["points"])


# ===========================================================================
# usda_bls_bridge — search_unified
# ===========================================================================

class TestSearchUnified:
    BLS_INDEX = [
        {"series_id": "APU0000706111", "item_name": "Chicken, fresh, whole, per lb.", "area_name": "U.S. city average"},
        {"series_id": "APU0000702111", "item_name": "Ground beef, 100% beef, per lb.", "area_name": "U.S. city average"},
        {"series_id": "APU0000711211", "item_name": "Whole milk, per gallon", "area_name": "U.S. city average"},
    ]

    def test_returns_both_sources(self):
        results = usda.search_unified("chicken", self.BLS_INDEX, limit=10)
        sources = {r["source"] for r in results}
        assert "usda" in sources
        assert "bls" in sources

    def test_results_sorted_by_score(self):
        results = usda.search_unified("chicken", self.BLS_INDEX, limit=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_min_score_filters_results(self):
        results_low  = usda.search_unified("chicken", self.BLS_INDEX, min_score=0.1)
        results_high = usda.search_unified("chicken", self.BLS_INDEX, min_score=0.9)
        assert len(results_low) >= len(results_high)

    def test_limit_respected(self):
        results = usda.search_unified("chicken", self.BLS_INDEX, limit=1)
        assert len(results) <= 1

    def test_no_match_returns_empty(self):
        results = usda.search_unified("zzznomatch", self.BLS_INDEX)
        assert results == []

    def test_result_has_required_fields(self):
        results = usda.search_unified("chicken", self.BLS_INDEX, limit=5)
        for r in results:
            for field in ("label", "source", "id", "score"):
                assert field in r, f"Missing field '{field}' in result"
