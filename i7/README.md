# **I7: API Access, create a simple API endpoint to host an information structure – BLS Food Price Dataset**
by Pete Namchaisiri for IMT542 (Sp 2026)

## **Overview**
This project implements a simple Flask API that exposes an information structure derived from the **Bureau of Labor Statistics (BLS) Average Price (AP) dataset**, specifically the **Food** subset (`ap.data.3.Food`).  
The API loads the dataset into memory, merges lookup tables, and provides endpoints to retrieve:

- A list of all food price series  
- Detailed observations for a specific series  
- Basic utility endpoints for testing (health check, greeting, echo)

The API is exposed publicly using **ngrok**, and accessed via Python `requests` as required by the assignment.

---

## **Video Demonstration**
A full walkthrough showing:

- Flask server running  
- ngrok tunnel  
- API access through ngrok  
- Python `requests.get()` demonstration  

**Video Link:**  
[https://drive.google.com/file/d/1GTA_Pq0VcoCUe9OiH4TOWzvYwnMKjfdl/view?usp=sharing](https://drive.google.com/file/d/1GTA_Pq0VcoCUe9OiH4TOWzvYwnMKjfdl/view?usp=sharing)

---

## **Dataset (BLS Average Price Data)**

The dataset used in this project comes from the **Bureau of Labor Statistics (BLS) Time Series Flat Files**, which provide complete historical datasets for many BLS programs.

The specific dataset used here is:

- **Average Price (AP) Dataset – Food Subset**  
- File: `ap.data.3.Food`  
- Contains monthly average retail prices for food items across U.S. regions

You can explore the full dataset directory here:

 **BLS Time Series Flat Files**  
`https://download.bls.gov/pub/time.series/`

The AP dataset folder is located at:

 **Average Price (AP) Dataset**  
`https://download.bls.gov/pub/time.series/ap/`

This directory includes:

- `ap.data.3.Food` — food price observations  
- `ap.series` — series metadata  
- `ap.item` — item lookup table  
- `ap.area` — geographic area lookup table  
- Documentation files describing the dataset structure  

These files are publicly available and updated regularly by the U.S. Bureau of Labor Statistics.


---

## **Project Structure**

```
.
├── app.py                 # Flask API server
├── ap.series              # BLS series lookup table
├── ap.data.3.Food         # BLS food price observations
├── ap.item                # Item lookup table
├── ap.area                # Area lookup table
└── README.md
```

---

## **API Endpoints**

### **GET /**  
Returns a welcome message.

**Example Response**
```json
{ "message": "Welcome to the i7 Flask API server" }
```

---

### **GET /api/health**  
Simple health check.

**Example Response**
```json
{ "status": "ok" }
```

---

### **GET /series**  
Returns all food price series with item and area names merged in.

**Example Response (truncated)**
```json
[
  {
    "series_id": "APU0000701111",
    "item_name": "Ground beef, 100% beef",
    "area_name": "U.S. city average"
  }
]
```

---

### **GET /data/<series_id>**  
Returns all observations for a specific series, grouped by year.

**Example Response**
```json
{
  "series_id": "APU0000701111",
  "item": "Ground beef, 100% beef",
  "area": "U.S. city average",
  "currency": "USD",
  "data_by_year": {
    "2024": [
      { "period": "M01", "value": 4.92 },
      { "period": "M02", "value": 4.95 }
    ]
  }
}
```

---

### **GET /api/greet?name=Pete**  
Returns a personalized greeting.

---

### **POST /api/echo**  
Echoes back any JSON payload.

---

## **Running the Project**

### **1. Install Dependencies**
```bash
pip install flask pandas
```

---

### **2. Run the Flask Server**
```bash
python app.py
```

The server will start on:

```
http://127.0.0.1:5000
```

---

### **3. Expose the API Using ngrok**
In a second terminal:

```bash
ngrok http 5000
```

Copy the generated URL, e.g.:

```
https://1234-56-78-910.ngrok-free.app
```

---

### **4. Test the API Using Python**
```python
import requests

url = "https://YOUR-NGROK-URL.ngrok-free.app/"
print(requests.get(url).text)
```

---

## **Notes**
- The dataset files (`ap.series`, `ap.data.3.Food`, `ap.item`, `ap.area`) come from the official BLS Time Series Flat Files.
- Column names and values are normalized to avoid whitespace issues.
- This API is intentionally simple and designed for demonstration purposes for the assignment.
- The final group project will expand this structure significantly.

---