# Food Nutrition–Cost Analysis Pipeline

by Pete Namchaisiri for IMT542 (Sp 2026)

This project integrates USDA Foundation Foods nutrition data with USDA Food-at-Home (F-MAP) price data to compute cost-efficiency metrics such as **calories per dollar**, **protein per dollar**, and **average price per 100g** for thousands of foods.

The notebook loads, cleans, maps, and analyzes both datasets using a lightweight fuzzy‑matching system (no external libraries required).

---

## Features

- Load USDA Foundation Foods JSON (calories + protein per 100g)
- Load F-MAP price data (price per 100g by food category and region)
- Auto-detect and parse the messy F-MAP metadata sheet
- Simple fuzzy-ish mapping from USDA foods → F-MAP EFPG categories
- Priority keyword rules to avoid incorrect matches (e.g., ricotta ≠ milk)
- Compute:
  - Average price per 100g
  - Calories per dollar
  - Protein per dollar
- Pretty-printed results for notebook readability

---

## Data Sources

### USDA Foundation Foods
- Nutrient composition per 100g (kcal, protein)
- Thousands of raw and processed foods

### USDA F-MAP (Food-at-Home Monthly Area Prices)
- Weighted mean price per 100g
- Monthly data (2012–2018)
- National, regional, and metro-level coverage
- EFPG food category taxonomy

---

## Pipeline Overview

1. **Load USDA nutrition JSON**
2. **Load F-MAP metadata (auto-detected header)**
3. **Load F-MAP price data**
4. **Merge price data with category dictionary**
5. **Map USDA foods → F-MAP categories**
   - Priority keyword rules
   - Simple similarity scoring
6. **Compute nutrition–cost metrics**
7. **Pretty-print or tabulate results**

---

## Example Usage

```python
search_term = "ricotta cheese"

# 1. Find USDA food
usda_row = usda_df[usda_df["food_name"].str.contains(search_term, case=False)].iloc[0]

# 2. Map to FAH category
fah_cat, method = map_food_to_fah(
    usda_row["food_name"],
    efpg_dict["EFPG_name"].tolist()
)

# 3. Compute nutrition vs cost
result = compute_nutrition_vs_cost(
    {
        "food_name": usda_row["food_name"],
        "fah_category": fah_cat,
        "calories_100g": usda_row["calories_100g"],
        "protein_100g": usda_row["protein_100g"]
    },
    fmap
)

print_result_pretty(result)
```

---

## Output Example

```
Food:                 Cheese, ricotta, whole milk
FAH Category:         Cheese and cream cheese
Avg Price / 100g:     $0.850
Calories per $:       410.2
Protein (g) per $:    28.4
```

---

## Requirements

- Python 3.8+
- pandas

No external fuzzy-matching libraries required.

---

## License

MIT License
