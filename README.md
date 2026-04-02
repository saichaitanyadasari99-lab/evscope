# EVScope Streamlit (Public)

Public Streamlit version of your EVScope dashboard for CAN-log analytics:
- DBC/DBF + ASC/LOG upload
- CAN frame decoding and signal reconstruction
- KPI cards (SOC, voltage, temperature, power)
- Dashboard + multi-panel plots
- Fault/anomaly detection
- CSV + PNG export

## Setup

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Publish to GitHub (Public)

```bash
git init
git add .
git commit -m "Initial public EVScope Streamlit app"
git branch -M main
git remote add origin https://github.com/<your-username>/evscope-streamlit-public.git
git push -u origin main
```

## Optional Hosting

- Streamlit Community Cloud
- Render
- Railway

## Streamlit Community Cloud

1. Push this project to GitHub.
2. In Streamlit Cloud, click `New app`.
3. Select repository: `saichaitanyadasari99-lab/evscope-streamlit-public`
4. Branch: `main`
5. Main file path: `app.py`
6. Deploy.
