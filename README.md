# BustRadar — AI Forecast-Bust Early Warning System
SIH 2026 · PS 26079 · NCMRWF / MoES

Predicts **where and when a Day 1–10 weather forecast is likely to fail**, and explains why.

## Repo layout (grows each day)
```
bustradar/
├── notebooks/
│   └── 01_data_pipeline.ipynb   Day 1 — run on Kaggle (Internet ON). Builds all data files.
├── data/                        put the unzipped bustradar_data/ here (git-ignored)
├── src/                         Day 2 — features, LightGBM, SHAP, analogues, U-Net
├── app/                         Day 3 — Streamlit dashboard + API + alerts
└── tests/mock_run.py            offline test of the notebook with synthetic data
```

## Day 1 — how to run
1. Kaggle → **New Notebook** → File → **Import Notebook** → upload `notebooks/01_data_pipeline.ipynb`.
2. Right panel → Settings → **Internet: On**. (No GPU needed.)
3. **Run all** with `QUICK_TEST = True` (one year, 2020). Check:
   - cell 3 lists the WeatherBench 2 stores and variables
   - cell 4 shows the estimated download size per variable
   - cell 7 prints the IMD date shift and a Day-1 correlation, which should be clearly positive (>0.5)
   - cell 10 draws the error-vs-lead chart. Error should rise with lead day.
4. Set `QUICK_TEST = False` and **Run all** again (2016–2022). Finished years are skipped.
5. Download `bustradar_data.zip` from the Output panel and unzip it into `data/`.

## Data sources
- **WeatherBench 2**: ECMWF IFS HRES forecasts + ERA5, 1.5° (gs://weatherbench2, public)
- **IMD** 0.25° gridded daily rainfall, via `imdlib`, the observed "truth" for rain
- Fallback if IMD download fails: ERA5 rainfall (the notebook switches automatically)

## Bust definition
For each region × lead day × season, a forecast is a **bust** if its grid RMSE (rain) or absolute
error (2 m temperature) is above the 90th percentile of the training years (2016–2020), with small
absolute floors (5 mm/day, 1.5 K). 2021–2022 are held out for testing and the event replays.
