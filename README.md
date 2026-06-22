# Argus Backend

Backend for the bachelor's thesis:
"Anomaly Detection in Environmental Time-Series Data with LLM-Assisted Interpretation for Forest Fire Early Warning".

Predicts forest fire risk in Finland from weather conditions, using historical
fire detections (EFFIS) and weather observations (FMI) to train a model.

## Folder structure
- `app/` - FastAPI app, services, models, database helpers
- `scripts/` - data pipeline scripts (cleaning fire data, fetching weather, training the model, DB init)
- `data/` - fire event and weather datasets used for training
- `models/` - trained model files (not committed, regenerate locally)
- `fire_events.json` - raw fire detections from EFFIS for Finland, 2015 onwards

## Setup (Windows / PowerShell)

### 1) Clone the repo
```powershell
git clone https://github.com/Seraj-Shekh/Argus.git
Set-Location Argus
```

### 2) Create and activate a virtual environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```powershell
pip install -r requirements.txt
```

### 4) Configure `.env`
Copy `.env` and fill in the DB values:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Argus_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
```

### 5) Create the database tables
Either run the ORM script:
```powershell
python .\scripts\init_db.py
```
or run `app\schemas\db.sql` manually in PgAdmin.

### 6) Run the API
```powershell
uvicorn app.main:app --reload
```
Then open `http://127.0.0.1:8000/`.

## Building the fire risk dataset and model

Data pipeline behind the fire risk model. `data/training_dataset.csv` is
already in the repo, so running steps 1 and 2 is only required to rebuild it.

```
fire_events.json -> load_fire_events.py -> fetch_fmi_weather.py -> training_dataset.csv -> train_model.py -> fire_risk_model.pkl
```

**1. Clean the raw fire events**
```powershell
python scripts/load_fire_events.py
```
Filters `fire_events.json` to Finland, 2015 onwards, confidence >= 80.
Writes `data/fire_events_clean.csv`.

**2. Fetch weather data**
```powershell
python scripts/fetch_fmi_weather.py
```
For each fire event, finds the nearest FMI weather station (within 50 km),
selects non-fire days at the same stations, and pulls daily weather
(temperature, humidity, wind speed, precipitation) from the FMI Open Data API.

This step makes tens of thousands of API calls on a first run. Results are
cached to `data/fmi_cache/`, so the script can be stopped and re-run without
re-fetching completed entries.

**3. Train the model**
```powershell
python scripts/train_model.py
```
Trains a Random Forest on `data/training_dataset.csv` and saves it to
`models/fire_risk_model.pkl`.
