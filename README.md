# Argus Backend 

Backend for the bachelor thesis project:
"Anomaly Detection in Environmental Time-Series Data with LLM-Assisted Interpretation for Forest Fire Early Warning".

## Folder structure
- `app/` - FastAPI app, services, models, database helpers
- `scripts/` - helper scripts (e.g., DB initialization)
- `data/` - sample data and fixtures (gitignored)

## Setup (Windows / PowerShell)

### 1) Clone and enter the backend folder
```powershell
git clone <REPO_URL>
Set-Location -Path '<YOUR_CLONE_PATH>\backend'
```

### 2) Create and activate the virtual environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```powershell
pip install -r requirements.txt
```
### 4) Configure `.env`
Copy `.env` and update the DB values:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Argus_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
```

### 5) Create tables (choose one)
Option A: create tables from ORM
```powershell
python .\scripts\init_db.py
```

Option B: create tables from `app\schemas\db.sql` in PgAdmin

## Run the API
```powershell
uvicorn app.main:app --reload
```

Open in browser:
- `http://127.0.0.1:8000/`

