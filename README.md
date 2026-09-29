# BustRadar — AI Forecast-Bust Early Warning System
SIH 2026 · PS 26079 · NCMRWF / MoES

Predicts **where and when a Day 1–10 weather forecast is likely to fail**, which kind of failure
(rain, heat, wind, large-scale pattern), which **weather system** is behind it, and explains why.

## Repo layout
```
bustradar/
├── notebooks/            run in order, each as a new cell in ONE Kaggle notebook (Internet ON)
│   ├── 01_data_pipeline      ECMWF forecasts (WeatherBench 2) + IMD rain -> region errors, bust labels
│   ├── 01b_extra_data        wind, Tmax, upper air, ERA5 z500, IMD Tmax, MJO / ENSO / IOD
│   ├── 02_models             5 bust types, system detectors, 120+ features, analogues, LightGBM, SHAP reasons
│   ├── 03_unet               U-Net deep ensemble: grid-level error-prone areas (optional, CPU or GPU)
│   ├── 04_dashboard          builds bustradar_dashboard.html (one file, works offline)
│   └── 05_live               LIVE: today's ECMWF open-data forecast -> BustRadar input (then 02 infer + 04)
├── app/
│   ├── dashboard_template.html   the dashboard UI
│   ├── build_bundle.py           same as notebook 04, for a laptop
│   ├── server.py                 dashboard + JSON API (standard library only)
│   ├── alerts.py                 state-wise English + Hindi bulletin, Telegram alerts (standard library only)
│   ├── live.py                   same as notebook 05, for a laptop or a daily cron job
│   └── states_india.json         Survey of India outline + state boundaries (DataMeet), mapped to the 1.5° grid
├── data/                 put bustradar_data/ and bustradar_models/ here (git-ignored)
└── tests/                offline tests with synthetic data (mock_run*.py)
```

## Run order (Kaggle)
1. `01_data_pipeline` (set `QUICK_TEST = False` for 2016–2022)
2. `01b_extra_data`
3. `02_models`
4. `03_unet` (optional: adds the grid-level "error-prone areas" map layer)
5. `04_dashboard` → download `bustradar_dashboard/bustradar_dashboard.html` and `bundle.json`

`02_models` has two modes (first code cell):
* `MODE = "train"` (default): builds features, **tunes** LightGBM (`TUNE = True`, `N_TRIALS = 12`, ~10–20 extra minutes),
  trains, calibrates, picks the alert threshold on the validation year, fits the 90% rainfall ranges, and saves every model.
* `MODE = "infer"`: loads the saved models and only predicts (no training). Used for live runs.

## Live mode (today's forecast)
```
pip install ecmwf-opendata cfgrib eccodes imdlib
python app/live.py                 # or notebook 05 on Kaggle: latest 4 ECMWF 00 UTC runs + IMD real-time rain
# notebook 02 with MODE = "infer"  (or: cd notebooks && python -c "MODE='infer'; exec(open('02_models.py').read())")
python app/build_bundle.py         # or notebook 04
```
Daily at 07:30 IST, a cron job can run the three steps and `python app/alerts.py --latest --telegram-token ... --telegram-chat ...`.
Live runs show a red LIVE RUN badge. Caveats: the ECMWF model has been upgraded since the 2016–2022 training years,
and a live run is only verified once IMD real-time rainfall for its valid dates is out (about a day later).

## Dashboard features
Region, **state/UT** and U-Net grid map layers · 10-day outlook · confidence matrix · detail panel with per-type
probabilities, **90% rainfall range**, weather systems, plain-language reasons (**English / हिन्दी**) and analogues ·
**state-wise or region-wise bulletin in English and Hindi** · **Yesterday's report card** (caught / missed / false
alarms, rainfall inside the range, last 30 days) · event replay · scorecard · API tab · dark/light theme button.

## Dashboard, API and alerts on a laptop (no pip install needed)
Put `bundle.json` in `app/dist/`, then:
```
python app/server.py                          # http://localhost:8000  (dashboard + API)
python app/alerts.py --date 2021-05-13        # text bulletin
python app/alerts.py --latest --telegram-token <token> --telegram-chat <chat id>
```
API: `/api/dates`, `/api/forecast?date=`, `/api/region?date=&region=`, `/api/states?date=`, `/api/alerts?date=&min_p=&by=state&lang=hi`,
`/api/report?date=`, `/api/events`, `/api/metrics`.

## Automatic daily updates (GitHub Actions + GitHub Pages)
`.github/workflows/daily.yml` runs every day at 14:15 IST on GitHub's servers: download today's ECMWF forecast →
predict with the saved models (`app/run_models.py --mode infer`) → build the dashboard → publish it on GitHub Pages.
The live history (for the report card) is kept in a release called `live-state`, updated by the job itself.

One-time setup:
1. Create a **public** repository and upload this folder (without `data/`).
2. **Releases → Draft a new release**, tag `data`, attach `bustradar_data.zip`, `bustradar_models.zip`
   (from a `MODE = "train"` run of the current notebook 02) and optionally `bustradar_unet.zip`. Publish.
3. **Settings → Pages → Source: GitHub Actions.**
4. **Actions tab → BustRadar daily live run → Run workflow** for the first run (about 30–60 min).
5. Optional Telegram: **Settings → Secrets and variables → Actions**: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT`.

The dashboard is then at `https://<user>.github.io/<repo>/` and updates itself daily. After re-training on Kaggle,
replace `bustradar_models.zip` in the `data` release. GitHub pauses scheduled jobs after 60 days without commits.

## Live link for judges
Create a GitHub repo, upload `bustradar_dashboard.html` renamed to `index.html`, then
Settings → Pages → Deploy from branch. The dashboard is then online at `https://<user>.github.io/<repo>/`.

## Data
- WeatherBench 2 (gs://weatherbench2): ECMWF IFS HRES forecasts, ERA5; 1.5° and 5.6°
- IMD 0.25° gridded rainfall and 1° Tmax, via `imdlib`
- MJO RMM (Australian Bureau of Meteorology), Niño-3.4 and DMI (NOAA PSL)
- Live: ECMWF open data (IFS 0.25°, CC-BY-4.0) and IMD real-time gridded rainfall
- Maps: Survey of India national outline and state boundaries via DataMeet (datameet.org)

## Bust definitions
Error above the 90th percentile for its region × lead day × season in the training years (2016–2020),
after removing each region's average bias, with small absolute floors (rain 5 mm/day, heat 1.5 K,
wind 2 m/s, 500 hPa 20 m). 2021–2022 are held out for testing and event replays.
