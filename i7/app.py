from flask import Flask, jsonify
import pandas as pd

app = Flask(__name__)

# Load BLS data into memory
series = pd.read_csv("data/ap.series", sep="\t")
data = pd.read_csv("data/ap.data.3.Food", sep="\t")
items = pd.read_csv("data/ap.item", sep="\t")
areas = pd.read_csv("data/ap.area", sep="\t")

series.columns = series.columns.str.strip().str.replace(" ", "_")
data.columns = data.columns.str.strip().str.replace(" ", "_")
items.columns = items.columns.str.strip().str.replace(" ", "_")
areas.columns = areas.columns.str.strip().str.replace(" ", "_")
def clean_df(df):
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    return df

series = clean_df(series)
data = clean_df(data)
items = clean_df(items)
areas = clean_df(areas)

# Merge lookup tables
series = series.merge(items, on="item_code").merge(areas, on="area_code")

print(f"Loaded {len(series)} series and {len(data)} data points")
print(data.head())
@app.route("/series")
def get_series():
    return jsonify(series.to_dict(orient="records"))

@app.route("/data/<series_id>")
def get_series_data(series_id):
    # Normalize incoming ID
    series_id = series_id.upper().strip()

    # Series metadata
    meta = series[series["series_id"] == series_id]
    if meta.empty:
        return jsonify({"error": "Series not found"}), 404

    # Observations
    subset = data[data["series_id"] == series_id]
    if subset.empty:
        return jsonify({"error": "No data for this series"}), 404

    # Group by year
    grouped = (
        subset
        .groupby("year")
        .apply(lambda g: g[["period", "value"]].to_dict(orient="records"), include_groups=False)
        .to_dict()
    )

    return jsonify({
        "series_id": series_id,
        "currency": "USD",
        "item": meta.iloc[0]["item_name"],
        "area": meta.iloc[0]["area_name"],
        "data_by_year": grouped
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Welcome to the i7 Flask API server"})

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/api/greet", methods=["GET"])
def greet():
    name = request.args.get("name", "world")
    return jsonify({"greeting": f"Hello, {name}!"})

@app.route("/api/echo", methods=["POST"])
def echo():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400
    return jsonify({"echo": data})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
