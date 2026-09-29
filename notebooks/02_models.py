# %% [markdown]
# # BustRadar — Day 2: Bust prediction with weather-system physics
#
# **Input:** `bustradar_data/` from notebooks **01** and **01b** (01b is optional; without it the
# heat/wind/pattern parts are skipped). **Runs on:** Kaggle CPU or a laptop, ~10–25 min.
#
# | step | what |
# |---|---|
# | Bust types | **rain**, **relative rain**, **heat (Tmax)**, **wind**, **500 hPa pattern**, and **any** |
# | Weather-system detectors | monsoon **depression**, **cyclone**, **western disturbance**, **heat wave**, **active/break** monsoon |
# | Predictability | lagged-ensemble spread, run-to-run jumps and pattern agreement, rain structure |
# | Physics | 850 hPa vorticity, 200–850 shear, 200 hPa jet, moisture flux convergence, instability (K-index, lapse rate), ascent, monsoon indices |
# | Climate drivers | MJO, ENSO, IOD, days since monsoon onset, current monsoon phase |
# | Memory | 7-day error history and trend, recent errors at longer leads, recent rain anomaly, neighbouring regions |
# | Analogues | 10 most similar past forecast maps and how often they busted |
# | Proof | vs climatology, vs a forecast-amount-only model, and vs the Day-2 v1 feature set |
# | Explain | SHAP → plain-language reasons naming the weather system (English + Hindi) |
# | Ranges | 90% rainfall range per region and day ("expect 12–48 mm/day"), conformal-calibrated |
# | Tuning | optional random search of the LightGBM settings on the validation year (`TUNE = True`) |
#
# **Two modes** (set in the first code cell):
# * `MODE = "train"` (default): builds everything and trains the models. Needed once, and again after code changes.
# * `MODE = "infer"`: loads the models saved by a previous `train` run and only predicts. Use it for
#   **live runs**: first run `python app/live.py` (downloads today's ECMWF forecast), then this notebook with
#   `MODE = "infer"`, then notebook 04 (or `python app/build_bundle.py`).

# %%
# ---- 1. Setup -----------------------------------------------------------------------------
import os, sys, glob, json, pickle, warnings, time, shutil
import numpy as np, pandas as pd, xarray as xr
def _load(path):
    with xr.open_dataset(path) as d:
        return d.load()
warnings.filterwarnings("ignore")
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

def find_data():
    cands = (glob.glob("/kaggle/working/bustradar_data/regions.parquet")
             + glob.glob("/kaggle/input/**/regions.parquet", recursive=True)
             + glob.glob("./data/bustradar_data/regions.parquet") + glob.glob("../data/bustradar_data/regions.parquet")
             + glob.glob("./bustradar_data/regions.parquet")
             + glob.glob("./**/regions.parquet", recursive=True) + glob.glob("./**/regions.csv.gz", recursive=True))
    if not cands:
        raise FileNotFoundError("regions.parquet not found. Run notebook 01 first, or set DATA manually.")
    return os.path.dirname(cands[0])

MODE = globals().get("MODE", "train")          # "train" = build + train (default) | "infer" = reuse saved models
TUNE = globals().get("TUNE", True)             # random search of LightGBM settings (train mode only, ~10-20 min)
N_TRIALS = globals().get("N_TRIALS", 12)

DATA = globals().get("DATA") or find_data()
OUT = globals().get("OUT2") or ("/kaggle/working/bustradar_models" if os.path.exists("/kaggle") else
                                ("../data/bustradar_models" if os.path.isdir("../data") else "./bustradar_models"))
os.makedirs(OUT, exist_ok=True)

def find_models():
    cands = ([OUT] + glob.glob("/kaggle/input/**/lgbm_bust.txt", recursive=True)
             + glob.glob("../data/bustradar_models/lgbm_bust.txt") + glob.glob("./data/bustradar_models/lgbm_bust.txt"))
    for c in cands:
        d = c if os.path.isdir(c) else os.path.dirname(c)
        if os.path.exists(os.path.join(d, "lgbm_bust.txt")) and os.path.exists(os.path.join(d, "model_meta.json")):
            return d
    raise FileNotFoundError("MODE = 'infer' needs the models from a MODE = 'train' run of THIS version of notebook 02 "
                            "(lgbm_bust.txt + model_meta.json). Run once with MODE = 'train'.")
MODELS_FROM = globals().get("MODELS_FROM") or (find_models() if MODE == "infer" else OUT)

FIT_YEARS, VAL_YEARS, TEST_YEARS = [2016, 2017, 2018, 2019], [2020], [2021, 2022]
LIVE_AFTER = 2022                                # forecasts after the archive are live runs (app/live.py)
def split_of(init):
    y = init.dt.year
    return np.select([y.isin(FIT_YEARS), y.isin(VAL_YEARS), y.isin(TEST_YEARS), y > LIVE_AFTER],
                     ["fit", "val", "test", "live"], "none")
split_of = globals().get("SPLIT_FN", split_of)

BUST_Q = 0.90
FLOORS = {"rain": 5.0, "heat": 1.5, "wind": 2.0, "z500": 20.0}      # mm/day, K, m/s, gpm
N_ANALOGS, ANALOG_WINDOW_DAYS, N_PCS, LAG_RUNS, SEED = 10, 45, 30, 3, 42
NEIGHBOURS = {"Himalayan WH": ["NW India"], "NE India": ["East India"],
              "NW India": ["Himalayan WH", "Central India"], "East India": ["NE India", "Central India"],
              "West Coast": ["Central India", "S. Peninsula"],
              "Central India": ["NW India", "East India", "West Coast", "S. Peninsula"],
              "S. Peninsula": ["West Coast", "Central India"]}
SYSTEM_REGIONS = {"depression": ["Central India", "East India", "NW India", "West Coast"],
                  "cyclone": ["East India", "S. Peninsula", "West Coast", "NE India"],
                  "wd": ["Himalayan WH", "NW India"]}
print("Data:", DATA, "| Output:", OUT, "| Mode:", MODE, "" if MODE == "train" else f"(models from {MODELS_FROM})")

# %%
# ---- 2. Load tables and maps ----------------------------------------------------------------
def read_table(stem):
    p = os.path.join(DATA, stem + ".parquet")
    return pd.read_parquet(p) if os.path.exists(p) else pd.read_csv(os.path.join(DATA, stem + ".csv.gz"))

df = read_table("regions")
if os.path.exists(os.path.join(DATA, "regions_live.parquet")) or os.path.exists(os.path.join(DATA, "regions_live.csv.gz")):
    live_rows = read_table("regions_live")                     # written by app/live.py (no observations yet)
    live_rows = live_rows[~pd.to_datetime(live_rows["init"]).isin(pd.to_datetime(df["init"]).unique())]
    df = pd.concat([df, live_rows], ignore_index=True)
    print("Live forecast runs added:", sorted(pd.to_datetime(live_rows["init"]).dt.date.astype(str).unique()))
df = df.drop(columns=[c for c in df.columns if c.startswith(("thr_", "sev_", "bust"))])   # recomputed below
df["init"] = pd.to_datetime(df["init"]); df["valid_date"] = pd.to_datetime(df["valid_date"])
df["split"] = split_of(df["init"])
with xr.open_dataset(os.path.join(DATA, "grid_meta.nc")) as _m:
    meta = _m.load()
REGION_NAMES = json.loads(meta.attrs["regions"]); R = len(REGION_NAMES)
TLAT, TLON = meta.lat.values, meta.lon.values
LAND, RID = meta.land.values.astype(bool), meta.region_id.values

def load_maps(prefix, dim):
    files = sorted(glob.glob(os.path.join(DATA, "maps", f"{prefix}_*.nc")))
    if not files: return None
    return xr.concat([_load(f) for f in files], dim=dim).sortby(dim)

fc = load_maps("fc", "init"); fcx = load_maps("fcx", "init")
fc = fc.isel(init=~pd.Index(fc.init.values).duplicated())
if fcx is not None: fcx = fcx.isel(init=~pd.Index(fcx.init.values).duplicated())
obs = load_maps("obs", "date"); obsx = load_maps("obsx", "date")
if obs is not None: obs = obs.isel(date=~pd.Index(obs.date.values).duplicated())
if obsx is not None: obsx = obsx.isel(date=~pd.Index(obsx.date.values).duplicated())
if fcx is not None:
    fcx = fcx.reindex(init=fc.init)
HAS_X = fcx is not None and obsx is not None
INITS = pd.DatetimeIndex(fc.init.values); NI, NL = len(INITS), fc.sizes["lead"]
LEADS = fc.lead.values
init_split = pd.Series(split_of(pd.Series(INITS)), index=INITS)
fit_i = (init_split == "fit").values

def csv_or_none(name):
    p = os.path.join(DATA, name)
    return pd.read_csv(p) if os.path.exists(p) else None
mjo, clim_mon = csv_or_none("climate_mjo_daily.csv"), csv_or_none("climate_monthly.csv")
if not (init_split == "fit").any() or not (init_split == "val").any():
    raise SystemExit(f"Only years {sorted(set(INITS.year))} found. BustRadar needs 2016-2022: set QUICK_TEST = False "
                     "in notebook 01, re-run 01 and 01b (finished years are skipped), then run 02 again.")
print(f"rows {len(df)} | inits {NI} | extra physics: {HAS_X} | MJO: {mjo is not None} | ENSO/IOD: {clim_mon is not None}")

# region weights (land cells only) for fast region means: (R, cells)
cells = RID.ravel()
W = np.stack([(cells == r).astype("float64") for r in range(R)])
W = W / np.maximum(W.sum(1, keepdims=True), 1)
BOX = lambda a0, a1, o0, o1: ((TLAT[:, None] >= a0) & (TLAT[:, None] <= a1) & (TLON[None, :] >= o0) & (TLON[None, :] <= o1))

def reg_mean(a):                       # (init, lead, lat, lon) -> (init, lead, R)
    x = np.nan_to_num(a.reshape(a.shape[0], a.shape[1], -1).astype("float64"))
    return np.einsum("ilc,rc->ilr", x, W)
def reg_max(a):
    x = a.reshape(a.shape[0], a.shape[1], -1)
    return np.stack([np.nanmax(np.where(cells == r, x, np.nan), axis=2) for r in range(R)], axis=2)
def box_stat(a, mask, fn):             # (init, lead, lat, lon) -> (init, lead)
    return fn(a[:, :, mask], axis=2)

def to_long(arr3, name):               # (init, lead, R) -> long DataFrame
    return pd.DataFrame({"init": np.repeat(INITS.values, NL * R), "lead": np.tile(np.repeat(LEADS, R), NI),
                         "region": np.tile(REGION_NAMES, NI * NL), name: arr3.ravel()})
def to_long_india(arr2, name):         # (init, lead) -> long, same for every region
    return to_long(np.repeat(arr2[:, :, None], R, axis=2), name)

def get(v):
    if v in fc: return fc[v].transpose("init", "lead", "lat", "lon").values.astype("float64")
    if HAS_X and v in fcx: return fcx[v].transpose("init", "lead", "lat", "lon").values.astype("float64")
    return None

V1_FEATURE_SNAPSHOT = None     # filled after the v1-style features are built (for the ablation)

# %%
# ---- 3. Gridded physics, predictability and weather-system detectors --------------------------
t0 = time.time()
feat = []                                  # list of long DataFrames to merge
MONTH = INITS.month.values

def month_clim(a):
    """Per-cell monthly mean of a forecast field over the fit years (all leads)."""
    c = np.full((13,) + a.shape[2:], np.nan)
    for m in range(1, 13):
        sel = fit_i & (MONTH == m)
        if sel.any(): c[m] = np.nanmean(a[sel], axis=(0, 1))
    return c
def anom(a):
    c = month_clim(a); return a - c[MONTH][:, None]

# spherical derivatives on the 1.5° grid
Re = 6.371e6
dy = np.deg2rad(1.5) * Re
dx = (np.deg2rad(1.5) * Re * np.cos(np.deg2rad(TLAT)))[:, None]
ddx = lambda f: np.gradient(f, axis=3) / dx
ddy = lambda f: np.gradient(f, axis=2) / dy

rain, mslp, z500 = get("rain"), get("mslp"), get("z500")
u850, v850, q700 = get("u850"), get("v850"), get("q700")
u200, v200, t500, t700, t850 = get("u200"), get("v200"), get("t500"), get("t700"), get("t850")
w500, q850, wind, tmax = get("w500"), get("q850"), get("wind10max"), get("tmax")

# --- rain structure
feat.append(to_long(reg_mean((rain > 10).astype(float)), "rain_frac10"))
rm = reg_mean(rain); rs = np.sqrt(np.maximum(reg_mean(rain ** 2) - rm ** 2, 0))
feat.append(to_long(rs / (rm + 1.0), "rain_cv"))

# --- lagged-ensemble spread: same valid day from this run and the previous LAG_RUNS runs
idx = pd.Index(INITS)
def lagged_stack(a):
    out = np.full((LAG_RUNS + 1,) + a.shape, np.nan, dtype="float32"); out[0] = a
    for k in range(1, LAG_RUNS + 1):
        pp = idx.get_indexer(INITS - pd.Timedelta(days=k)); ok = pp >= 0
        out[k][ok, :NL - k] = a[pp[ok], k:]
    return out
def lag_spread(a):
    st = lagged_stack(a); n = np.isfinite(st).sum(0)
    sd = np.nanstd(st, axis=0); sd[n < 2] = np.nan
    return sd
LAGGED = {"rain": None if rain is None else np.log1p(np.clip(rain, 0, None)), "z500": z500, "mslp": mslp,
          "tmax": tmax, "wind10max": wind}
for v, a in LAGGED.items():
    if a is None: continue
    feat.append(to_long(reg_mean(lag_spread(a)), f"lag_spread_{v}"))

# --- run-to-run pattern agreement (spatial correlation with yesterday's run for the same day)
def patcorr_prev(a, mask=None):
    pp = idx.get_indexer(INITS - pd.Timedelta(days=1)); ok = pp >= 0
    out = np.full((NI, NL), np.nan)
    A = a.reshape(NI, NL, -1)
    if mask is not None: A = A[:, :, mask.ravel()]
    cur, prev = A[ok, :NL - 1], A[pp[ok], 1:]
    cur = cur - np.nanmean(cur, 2, keepdims=True); prev = prev - np.nanmean(prev, 2, keepdims=True)
    r = np.nansum(cur * prev, 2) / np.sqrt(np.nansum(cur ** 2, 2) * np.nansum(prev ** 2, 2) + 1e-12)
    out[ok, :NL - 1] = r
    return out
if z500 is not None: feat.append(to_long_india(patcorr_prev(anom(z500)), "india_z500_patcorr"))
if rain is not None:
    lr = np.log1p(np.clip(rain, 0, None))
    feat.append(to_long_india(patcorr_prev(lr, LAND), "india_rain_patcorr"))
    per = np.stack([patcorr_prev(lr, RID == r) for r in range(R)], axis=2)
    feat.append(to_long(per, "rain_patcorr"))

# --- physics
if u850 is not None and v850 is not None:
    vort = (ddx(v850) - ddy(u850)) * 1e5                                     # 1e-5 s-1
    feat += [to_long(reg_mean(vort), "vort850"), to_long(reg_max(vort), "vort850_max")]
    if q700 is not None or q850 is not None:
        q = q850 if q850 is not None else q700
        mfc = -(ddx(q * u850) + ddy(q * v850)) * 1e5                         # g/kg per 1e5 s
        feat += [to_long(reg_mean(mfc), "mfc850"), to_long(reg_mean(q * np.hypot(u850, v850)), "ivt850")]
if u200 is not None and v200 is not None:
    feat.append(to_long(reg_mean(np.hypot(u200, v200)), "jet200"))
    if u850 is not None:
        feat.append(to_long(reg_mean(np.hypot(u200 - u850, v200 - v850)), "shear200_850"))
        wy = box_stat(u850 - u200, BOX(6, 20, 66, 100.5), np.nanmean)       # Webster-Yang-like monsoon index
        feat.append(to_long_india(wy, "monsoon_shear_index"))
if u850 is not None:
    feat.append(to_long_india(box_stat(u850, BOX(6, 15, 66, 75), np.nanmean), "arabian_llj"))
if w500 is not None:
    feat.append(to_long(reg_mean(-w500), "ascent500"))                       # Pa/s, positive = rising air
if t500 is not None and t850 is not None:
    feat.append(to_long(reg_mean(t850 - t500), "lapse850_500"))
    if t700 is not None and q700 is not None and q850 is not None:
        def dewpoint(qgkg, p):
            e = (qgkg / 1000) * p / (0.622 + 0.378 * qgkg / 1000)
            l = np.log(np.clip(e, 1e-3, None) / 6.112); return 243.5 * l / (17.67 - l)
        C = lambda T: T - 273.15
        ki = (C(t850) - C(t500)) + dewpoint(q850, 850) - (C(t700) - dewpoint(q700, 700))
        feat.append(to_long(reg_mean(ki), "k_index"))

# --- weather-system detectors (heuristics on the forecast; thresholds are tunable)
SYS = {}
SEA = ~LAND
if mslp is not None:
    mslp_a = anom(mslp)
    feat.append(to_long_india(box_stat(mslp_a, BOX(15, 24, 80, 95), np.nanmin), "bay_low_anom"))
    feat.append(to_long_india(box_stat(mslp_a, BOX(18, 26, 74, 88), np.nanmin), "central_low_anom"))
    band = BOX(15, 30, 75, 85)
    ml = np.where(band, mslp, np.nan).reshape(NI, NL, -1)
    tl = np.where(band, np.broadcast_to(TLAT[:, None], band.shape), np.nan).ravel()
    arg = np.nanargmin(np.where(np.isfinite(ml), ml, np.inf), axis=2)
    feat.append(to_long_india(tl[arg], "monsoon_trough_lat"))
    vort_max_core = box_stat(vort, BOX(15, 26, 75, 92), np.nanmax) if u850 is not None else np.zeros((NI, NL))
    low_min = np.minimum(box_stat(mslp_a, BOX(15, 24, 80, 95), np.nanmin), box_stat(mslp_a, BOX(18, 26, 74, 88), np.nanmin))
    jjas = np.isin(MONTH, [6, 7, 8, 9])[:, None]
    SYS["depression"] = (jjas & (low_min < -5.0) & (vort_max_core > 1.5)).astype(float)
    sea_box = SEA & BOX(5, 22, 66, 95)
    sea_low = box_stat(mslp_a, sea_box, np.nanmin)
    sea_wind = box_stat(wind, sea_box, np.nanmax) if wind is not None else np.full((NI, NL), 99.0)
    SYS["cyclone"] = ((sea_low < -8.0) & (sea_wind > 14.0)).astype(float)
    feat += [to_long_india(sea_low, "sea_low_anom"), to_long_india(sea_wind, "sea_wind_max")]
if z500 is not None:
    z500_a = anom(z500)
    wd_z = box_stat(z500_a, BOX(28, 40.5, 66, 80), np.nanmin)
    feat.append(to_long_india(wd_z, "wd_trough_anom"))
    jet_nw = box_stat(u200, BOX(25, 40.5, 66, 80), np.nanmax) if u200 is not None else np.zeros((NI, NL))
    feat.append(to_long_india(jet_nw, "wd_jet_max"))
    winter = np.isin(MONTH, [10, 11, 12, 1, 2, 3, 4])[:, None]
    SYS["wd"] = (winter & (wd_z < -60.0) & (jet_nw > 30.0)).astype(float)
for k, v in SYS.items():
    arr = np.repeat(v[:, :, None], R, axis=2)
    arr = arr * np.isin(REGION_NAMES, SYSTEM_REGIONS[k])[None, None, :]     # only where the system matters
    feat.append(to_long(arr, f"sys_{k}"))

# --- extra forecast variables as region means
for v, a in {"wind10max": wind, "tmax": tmax, "u200": u200, "v200": v200, "t850": t850, "q850": q850}.items():
    if a is not None: feat.append(to_long(reg_mean(a), f"fc_{v}"))
if wind is not None: feat.append(to_long(reg_max(wind), "fc_wind10max_max"))

for f in feat:
    df = df.merge(f, on=["init", "lead", "region"], how="left")
print(f"Gridded features done in {time.time() - t0:.0f}s | system flags: "
      + ", ".join(f"{k} {100 * v.mean():.1f}%" for k, v in SYS.items()))

# %%
# ---- 4. Truth for all bust types + labels ------------------------------------------------------
train_mask = df["split"].isin(["fit", "val"])
valid = INITS.values[:, None] + (LEADS - 1)[None, :] * np.timedelta64(1, "D")

def obs_on_forecast(o):                     # (date, lat, lon) -> (init, lead, lat, lon)
    pos = pd.Index(pd.DatetimeIndex(o.date.values)).get_indexer(valid.ravel())
    a = o.transpose("date", "lat", "lon").values.astype("float64")
    g = np.full((valid.size,) + a.shape[1:], np.nan); g[pos >= 0] = a[pos[pos >= 0]]
    return g.reshape(NI, NL, *a.shape[1:])

def region_errors(fc_a, ob_a, name):
    e = fc_a - ob_a; m = np.isfinite(e)
    cnt = np.einsum("ilc,rc->ilr", m.reshape(NI, NL, -1).astype(float), (W > 0).astype(float))
    s1 = np.einsum("ilc,rc->ilr", np.nan_to_num(e).reshape(NI, NL, -1), (W > 0).astype(float))
    s2 = np.einsum("ilc,rc->ilr", np.nan_to_num(e ** 2).reshape(NI, NL, -1), (W > 0).astype(float))
    me = np.where(cnt > 0, s1 / np.maximum(cnt, 1), np.nan); mse = np.where(cnt > 0, s2 / np.maximum(cnt, 1), np.nan)
    ob_mean = np.where(cnt > 0, np.einsum("ilc,rc->ilr", np.nan_to_num(ob_a).reshape(NI, NL, -1), (W > 0).astype(float)) / np.maximum(cnt, 1), np.nan)
    out = to_long(me, f"{name}_err")
    out[f"{name}_mse"] = mse.ravel(); out[f"obs_{name}"] = ob_mean.ravel()
    return out

def label(col, name, floor, use_bias=True):
    """Bias-correct (region x lead x month, fit years) then label errors above the 90th percentile."""
    global df
    if use_bias:
        b = df[df.split == "fit"].groupby(["region", "lead", "month"])[f"{name}_err"].mean().rename(f"{name}_bias").reset_index()
        df = df.merge(b, on=["region", "lead", "month"], how="left"); df[f"{name}_bias"] = df[f"{name}_bias"].fillna(0)
        # RMSE after removing the bias:  MSE - 2*b*mean_err + b^2
        df[col] = np.sqrt(np.clip(df[f"{name}_mse"] - 2 * df[f"{name}_bias"] * df[f"{name}_err"] + df[f"{name}_bias"] ** 2, 0, None))
    thr = (df[train_mask].groupby(["region", "lead", "season"])[col].quantile(BUST_Q).clip(lower=floor)
           .rename(f"thr_{col}").reset_index())
    df = df.drop(columns=[f"thr_{col}"], errors="ignore").merge(thr, on=["region", "lead", "season"], how="left")
    return (df[col] > df[f"thr_{col}"]).astype(int)

# rain (from notebook 01) + relative rain
df["bust_rain"] = label("rain_rmse", "rain", FLOORS["rain"], use_bias=False)
df["rain_nrmse"] = df["rain_rmse"] / (0.5 * (df["fc_rain"].clip(lower=0) + df["obs_rain"].clip(lower=0)) + 2.0)
df["bust_rain_rel"] = label("rain_nrmse", "rain_nrmse", 0.0, use_bias=False)
TARGETS = ["bust_rain", "bust_rain_rel"]

if HAS_X and tmax is not None and "tmax" in obsx:
    df = df.merge(region_errors(tmax, obs_on_forecast(obsx["tmax"]), "heat"), on=["init", "lead", "region"], how="left")
    b = df[df.split == "fit"].groupby(["region", "lead", "month"])["heat_err"].mean().rename("heat_bias").reset_index()
    df = df.merge(b, on=["region", "lead", "month"], how="left"); df["heat_bias"] = df["heat_bias"].fillna(0)
    df["heat_abs_bc"] = (df["heat_err"] - df["heat_bias"]).abs()          # region-mean Tmax error, bias removed
    df["bust_heat"] = label("heat_abs_bc", "heat", FLOORS["heat"], use_bias=False)
    df["fc_tmax_bc"] = df["fc_tmax"] - df["heat_bias"]
    TARGETS.append("bust_heat")
    print("Heat truth:", obsx.attrs.get("tmax_source", "?"), "| mean |Tmax error| raw -> bias-corrected:",
          round(df.heat_err.abs().mean(), 2), "->", round(df.heat_abs_bc.mean(), 2), "K")
elif "t2m_err" in df:                                                     # fallback: notebook-01 temperature
    b = df[df.split == "fit"].groupby(["region", "lead", "month"])["t2m_err"].mean().rename("t2m_bias").reset_index()
    df = df.merge(b, on=["region", "lead", "month"], how="left"); df["t2m_bias"] = df["t2m_bias"].fillna(0)
    df["heat_abs_bc"] = (df["t2m_err"] - df["t2m_bias"]).abs(); df["fc_tmax_bc"] = df["fc_t2m"] - df["t2m_bias"]
    df["bust_heat"] = label("heat_abs_bc", "heat", FLOORS["heat"], use_bias=False); TARGETS.append("bust_heat")
if HAS_X and wind is not None and "wind10max" in obsx:
    df = df.merge(region_errors(wind, obs_on_forecast(obsx["wind10max"]), "wind"), on=["init", "lead", "region"], how="left")
    df["bust_wind"] = label("wind_rmse_bc", "wind", FLOORS["wind"]); TARGETS.append("bust_wind")
if HAS_X and z500 is not None and "z500" in obsx:
    df = df.merge(region_errors(z500, obs_on_forecast(obsx["z500"]), "z500"), on=["init", "lead", "region"], how="left")
    df["bust_z500"] = label("z500_rmse_bc", "z500", FLOORS["z500"]); TARGETS.append("bust_z500")

ANY = [t for t in TARGETS if t != "bust_rain_rel"]
df["bust"] = df[ANY].max(axis=1)
TARGETS = ANY + ["bust", "bust_rain_rel"]
VERIFIED = df["obs_rain"].notna()          # live runs are not verified yet: their labels are blanked when saving
print("Bust rates by split:"); print(df.groupby("split")[TARGETS].mean().round(3))

# %%
# ---- 5. Anomalies, jumps, climate drivers, memory, neighbours ---------------------------------------
FC_COLS = [c for c in df.columns if c.startswith("fc_") and not c.endswith(("_anom", "_bc"))]
clim = df[df.split == "fit"].groupby(["region", "month"])[FC_COLS].mean().add_suffix("_clim").reset_index()
df = df.merge(clim, on=["region", "month"], how="left")
for c in FC_COLS:
    df[c + "_anom"] = df[c] - df[c + "_clim"]
df = df.drop(columns=[c + "_clim" for c in FC_COLS])

# jumps for every forecast column (notebook 01 already made jump_ for its variables)
prev = df[["init", "lead", "region"] + FC_COLS].copy()
prev["init"] = prev["init"] + pd.Timedelta(days=1); prev["lead"] = prev["lead"] - 1
prev = prev.rename(columns={c: c + "_prev" for c in FC_COLS})
df = df.merge(prev, on=["init", "lead", "region"], how="left")
for c in FC_COLS:
    j = c.replace("fc_", "jump_")
    if j not in df: df[j] = df[c] - df[c + "_prev"]
    df[j + "_abs"] = df[j].abs()
df = df.drop(columns=[c + "_prev" for c in FC_COLS])

# calendar + identity
doy = df["valid_date"].dt.dayofyear
df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
df["region_code"] = df["region"].map({r: i for i, r in enumerate(REGION_NAMES)}).astype(int)
for c in [v for v in ["fc_z500_anom", "fc_q700_anom", "fc_rain_anom"] if v in df]:
    df["india_" + c] = df.groupby(["init", "lead"])[c].transform("mean")

# --- memory of recent errors (all verified before the forecast is issued)
d1 = df[df.lead == 1][["region", "valid_date", "rain_rmse", "obs_rain"] + (["heat_abs_bc"] if "heat_abs_bc" in df else [])]
def lagged_mean(frame, cols, lags, prefix):
    parts = []
    for lag in lags:
        x = frame.copy(); x["init"] = x["valid_date"] + pd.Timedelta(days=lag); parts.append(x.drop(columns="valid_date"))
    return pd.concat(parts).groupby(["region", "init"])[cols].mean().add_prefix(prefix).reset_index()
mem_cols = [c for c in ["rain_rmse", "heat_abs_bc"] if c in d1]
df = df.merge(lagged_mean(d1, mem_cols, (1, 2, 3), "recent_"), on=["region", "init"], how="left")
m7 = lagged_mean(d1, mem_cols + ["obs_rain"], range(1, 8), "week_")
m4 = lagged_mean(d1, ["rain_rmse"], range(4, 8), "older_")
df = df.merge(m7, on=["region", "init"], how="left").merge(m4, on=["region", "init"], how="left")
df["rain_err_trend"] = df["recent_rain_rmse"] - df["older_rain_rmse"]
rain_clim = df[df.split == "fit"].groupby(["region", "month"])["obs_rain"].mean().rename("_rc").reset_index()
df = df.merge(rain_clim, on=["region", "month"], how="left")
df["week_rain_anom"] = df["week_obs_rain"] - df["_rc"]
df = df.drop(columns=["_rc", "older_rain_rmse", "week_obs_rain"])
for L in (3, 5):                           # errors of longer-lead forecasts that verified yesterday
    x = df[df.lead == L][["region", "valid_date", "rain_rmse"]].copy()
    x["init"] = x["valid_date"] + pd.Timedelta(days=1)
    df = df.merge(x.drop(columns="valid_date").rename(columns={"rain_rmse": f"recent_rain_rmse_d{L}"}), on=["region", "init"], how="left")

# --- monsoon onset (Kerala) and phase (core monsoon zone), from observed IMD rain
if obs is not None and "rain" in obs:
    o_rain = obs["rain"].transpose("date", "lat", "lon")
    dates = pd.DatetimeIndex(o_rain.date.values)
    kerala = LAND & BOX(8, 12.5, 74.5, 77.5); cmz = LAND & BOX(18, 28, 65, 88)
    ker = pd.Series(np.nanmean(o_rain.values[:, kerala], 1), index=dates)
    # IMD's declared Kerala onset dates (known on the day they were declared). Other years: rain >= 8 mm/day
    # on 3 consecutive days AND >= 10 mm/day averaged over the following week (filters pre-monsoon showers).
    IMD_ONSET = {2016: "2016-06-08", 2017: "2017-05-30", 2018: "2018-05-29", 2019: "2019-06-08",
                 2020: "2020-06-01", 2021: "2021-06-03", 2022: "2022-05-29"}
    onset = {}
    for y in sorted(set(dates.year)):
        if y in IMD_ONSET: onset[y] = pd.Timestamp(IMD_ONSET[y]); continue
        s = ker[(ker.index >= f"{y}-05-10") & (ker.index <= f"{y}-07-15")]
        ok = (s.rolling(3).min() >= 8.0).shift(-2) & (s[::-1].rolling(7).mean()[::-1] >= 10.0)
        if ok.any(): onset[y] = ok[ok].index[0]
    on = pd.to_datetime(df["init"].dt.year.map(onset))
    dso = (df["init"] - on).dt.days
    df["days_since_onset"] = np.where(dso >= 0, dso, np.nan)
    cm = pd.Series(np.nanmean(o_rain.values[:, cmz], 1), index=dates)
    tr = cm[cm.index.year.isin(FIT_YEARS + VAL_YEARS)]
    dclim = tr.groupby(tr.index.dayofyear).agg(["mean", "std"]).reindex(range(1, 367)).interpolate(limit_direction="both")
    dclim = pd.concat([dclim.iloc[-15:], dclim, dclim.iloc[:15]]).rolling(31, center=True).mean().iloc[15:-15]
    dclim.index = range(1, 367)
    cm_std = (cm - dclim["mean"].reindex(cm.index.dayofyear).values) / (dclim["std"].reindex(cm.index.dayofyear).values + 0.5)
    # observed phase on each valid day (for the analysis in section 10) ...
    run = lambda s, cond: cond.groupby((cond != cond.shift()).cumsum()).transform("sum").where(cond, 0) >= 3
    jjas = cm_std.index.month.isin([6, 7, 8, 9])
    PHASE = pd.Series("normal", index=cm_std.index)
    PHASE[run(cm_std, (cm_std > 1.0) & jjas)] = "active"; PHASE[run(cm_std, (cm_std < -1.0) & jjas)] = "break"
    PHASE[~jjas] = "off-season"
    df["obs_monsoon_phase"] = df["valid_date"].map(PHASE)
    # ... and, as features, the phase known at issue time and the forecast phase
    rec = cm_std.rolling(3).mean().shift(1)
    df["cmz_anom_now"] = df["init"].map(rec)
    if rain is not None:
        fc_cmz = box_stat(rain, cmz, np.nanmean)
        mu = dclim["mean"].reindex(pd.DatetimeIndex(valid.ravel()).dayofyear).values.reshape(NI, NL)
        sd = dclim["std"].reindex(pd.DatetimeIndex(valid.ravel()).dayofyear).values.reshape(NI, NL) + 0.5
        df = df.merge(to_long_india((fc_cmz - mu) / sd, "cmz_anom_fc"), on=["init", "lead", "region"], how="left")
        df["phase_change_fc"] = df["cmz_anom_fc"] - df["cmz_anom_now"]
        jj = df["valid_date"].dt.month.isin([6, 7, 8, 9])
        df["sys_active"] = ((df["cmz_anom_fc"] > 1.0) & jj).astype(float)
        df["sys_break"] = ((df["cmz_anom_fc"] < -1.0) & jj).astype(float)
    print("Monsoon onset dates:", {y: str(d.date()) for y, d in onset.items()})

# --- heat-wave flag (forecast): IMD-style departure >= 4.5 K or Tmax >= 40 °C in the hot season
if "fc_tmax_anom" in df:
    hot = df["valid_date"].dt.month.isin([3, 4, 5, 6])
    df["sys_heatwave"] = (hot & ((df["fc_tmax_anom"] >= 4.5) | (df["fc_tmax_bc"] >= 313.15))).astype(float)

# --- climate drivers
if mjo is not None:
    mj = mjo.assign(date=pd.to_datetime(mjo["date"])).set_index("date")
    mj.index = mj.index + pd.Timedelta(days=1)                           # yesterday's value is what we know
    for c in ["rmm1", "rmm2", "mjo_amp"]:
        df[c] = df["init"].map(mj[c])
    ph = df["init"].map(mj["mjo_phase"])
    df["mjo_phase_sin"], df["mjo_phase_cos"] = np.sin(2 * np.pi * ph / 8), np.cos(2 * np.pi * ph / 8)
if clim_mon is not None:
    cmn = clim_mon.copy()
    cmn["key"] = pd.to_datetime(dict(year=cmn.year, month=cmn.month, day=1)) + pd.DateOffset(months=1)  # last month's value
    key = df["init"].dt.to_period("M").dt.to_timestamp()
    for c in [x for x in ["nino34", "iod_dmi"] if x in cmn]:
        df[c] = key.map(cmn.set_index("key")[c])

# --- neighbouring regions
for c in [x for x in ["jump_rain_abs", "lag_spread_rain", "fc_rain_anom", "vort850"] if x in df]:
    piv = df.pivot_table(index=["init", "lead"], columns="region", values=c)
    nb = pd.DataFrame({r: piv[[n for n in NEIGHBOURS.get(r, []) if n in piv]].mean(axis=1) for r in REGION_NAMES})
    nb = nb.stack().rename(f"nbr_{c}").reset_index().rename(columns={"level_2": "region"})
    nb.columns = ["init", "lead", "region", f"nbr_{c}"]
    df = df.merge(nb, on=["init", "lead", "region"], how="left")
print("Columns now:", df.shape[1])

# %%
# ---- 6. Analogue engine: "this forecast looks like ..." -------------------------------------------
t0 = time.time()
MAP_SRC = {"rain": rain, "z500": z500, "q700": q700, "u850": u850, "v850": v850, "mslp": mslp,
           "tmax": tmax, "wind10max": wind, "u200": u200}
MAP_SRC = {k: v for k, v in MAP_SRC.items() if v is not None}
lab = {t: df.pivot_table(index=["init", "lead"], columns="region", values=t) for t in ["bust_rain", "bust"]}
analog_rows, analog_dates = [], {}
lib_mask = init_split.isin(["fit", "val"]).values; lib_idx = np.where(lib_mask)[0]
doy_all, yr_all = INITS.dayofyear.values, INITS.year.values
for li, L in enumerate(LEADS):
    X = []
    for v, a in MAP_SRC.items():
        x = a[:, li].reshape(NI, -1)
        if v == "rain": x = np.log1p(np.clip(x, 0, None))
        mu, sd = np.nanmean(x[lib_mask], 0), np.nanstd(x[lib_mask], 0) + 1e-6
        X.append(np.nan_to_num((x - mu) / sd))
    X = np.concatenate(X, 1)
    pca = PCA(n_components=min(N_PCS, lib_mask.sum() - 1, X.shape[1]), random_state=SEED).fit(X[lib_mask])
    Z = pca.transform(X)
    nn = NearestNeighbors(n_neighbors=min(len(lib_idx), N_ANALOGS * 8)).fit(Z[lib_idx])
    dist, nbr = nn.kneighbors(Z)
    for q in range(NI):
        cand = lib_idx[nbr[q]]
        dd = np.abs(doy_all[cand] - doy_all[q]); dd = np.minimum(dd, 365 - dd)
        keep = (yr_all[cand] != yr_all[q]) & (dd <= ANALOG_WINDOW_DAYS)
        chosen, cd = cand[keep][:N_ANALOGS], dist[q][keep][:N_ANALOGS]
        if len(chosen) == 0: continue
        w = 1.0 / (cd + 1e-6); w = w / w.sum()
        row = {"init": INITS[q], "lead": L, "analog_dist": float(cd.mean())}
        for t, tab in lab.items():
            br = tab.reindex([(INITS[c], L) for c in chosen]).values
            rates = np.nansum(br * w[:, None], 0) / np.maximum((np.isfinite(br) * w[:, None]).sum(0), 1e-9)
            rates = np.where(np.isfinite(br).any(0), rates, np.nan)
            row.update({f"{t}|{r}": v for r, v in zip(tab.columns, rates)})
        analog_rows.append(row)
        analog_dates[(str(INITS[q].date()), int(L))] = [str(INITS[c].date()) for c in chosen[:3]]
    print(f"lead {L}: {pca.n_components_} PCs explain {pca.explained_variance_ratio_.sum():.0%}")
an = pd.DataFrame(analog_rows)
for t, name in [("bust_rain", "analog_rain_bust_rate"), ("bust", "analog_bust_rate")]:
    cols = [c for c in an.columns if c.startswith(t + "|")]
    lg = an.melt(id_vars=["init", "lead"], value_vars=cols, var_name="region", value_name=name)
    lg["region"] = lg["region"].str.split("|").str[1]
    df = df.merge(lg, on=["init", "lead", "region"], how="left")
df = df.merge(an[["init", "lead", "analog_dist"]], on=["init", "lead"], how="left")
print(f"Analogues done in {time.time() - t0:.0f}s")

# %%
# ---- 7. Train models: full BustRadar, v1 feature set, forecast-amount-only ------------------------
EXCLUDE = {"init", "valid_date", "region", "split", "season", "month", "obs_monsoon_phase",
           "rain_rmse", "rain_err", "rain_nrmse", "t2m_err", "t2m_abs", "t2m_rmse", "t2m_abs_bc", "t2m_bias",
           "heat_err", "heat_mse", "heat_bias", "heat_abs_bc", "wind_err", "wind_mse", "wind_bias", "wind_rmse_bc",
           "z500_err", "z500_mse", "z500_bias", "z500_rmse_bc"}
# everything numeric that is known at issue time (no observations of the target day, no labels)
FEATURES = [c for c in df.columns if c not in EXCLUDE and pd.api.types.is_numeric_dtype(df[c])
            and not c.startswith(("obs_", "thr_", "sev_", "bust", "p_"))]
V1_FEATURES = [c for c in FEATURES if c in {
    "lead", "fc_rain", "fc_t2m", "fc_mslp", "fc_z500", "fc_u850", "fc_v850", "fc_q700", "fc_rain_max",
    "doy_sin", "doy_cos", "region_code", "analog_dist", "analog_bust_rate", "recent_rain_rmse", "recent_heat_abs_bc",
    "india_fc_z500_anom", "india_fc_q700_anom", "india_fc_rain_anom"}
    or (c.startswith(("jump_", "fc_")) and any(v in c for v in ["rain", "t2m", "mslp", "z500", "u850", "v850", "q700"])
        and not any(v in c for v in ["tmax", "wind10", "u200", "v200", "t850", "q850"]))]
BASE_FEATS = [c for c in ["lead", "region_code", "doy_sin", "doy_cos", "fc_rain", "fc_rain_max", "fc_t2m",
                          "fc_tmax", "fc_tmax_bc", "fc_wind10max", "fc_wind10max_max"] if c in df]
print(f"{len(FEATURES)} features (v1 set: {len(V1_FEATURES)}, amount-only: {len(BASE_FEATS)})")

fit, val = df[df.split == "fit"], df[df.split == "val"]
PARAMS = dict(n_estimators=3000, learning_rate=0.03, num_leaves=31, min_child_samples=60,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=2.0, random_state=SEED, verbose=-1)
def train(feats, t, calibrate=True, params=None, patience=150):
    pos = fit[t].mean()
    m = lgb.LGBMClassifier(**(params or PARAMS), scale_pos_weight=max(1.0, (1 - pos) / max(pos, 1e-6)) ** 0.5)
    m.fit(fit[feats], fit[t], eval_set=[(val[feats], val[t])], eval_metric="binary_logloss",
          categorical_feature=["region_code"] if "region_code" in feats else "auto",
          callbacks=[lgb.early_stopping(patience, verbose=False)])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(m.predict_proba(val[feats])[:, 1], val[t]) if calibrate else None
    return m, iso

class Saved:
    """A LightGBM model loaded from disk that behaves like the trained LGBMClassifier."""
    def __init__(self, path): self.booster_ = lgb.Booster(model_file=path); self.best_iteration_ = self.booster_.current_iteration()
    def predict_proba(self, X): p = self.booster_.predict(X); return np.column_stack([1 - p, p])
    def predict(self, X, **kw): return self.booster_.predict(X, **kw)

if MODE == "infer":
    mm = json.load(open(os.path.join(MODELS_FROM, "model_meta.json")))
    missing = [c for c in mm["features"] if c not in df]
    if missing: print("Features missing in this data (set to NaN):", missing[:10], "..." if len(missing) > 10 else "")
    for c in missing: df[c] = np.nan
    FEATURES, TARGETS = mm["features"], [t for t in mm["targets"] if t in df]
    V1_FEATURES, BASE_FEATS = mm.get("v1_features", V1_FEATURES), mm.get("base_features", BASE_FEATS)
    fit, val = df[df.split == "fit"], df[df.split == "val"]
    ld = lambda f: Saved(os.path.join(MODELS_FROM, f)) if os.path.exists(os.path.join(MODELS_FROM, f)) else None
    models = {t: ld(f"lgbm_{t}.txt") for t in TARGETS}
    v1_models = {t: ld(f"lgbm_v1_{t}.txt") for t in TARGETS}; amt_models = {t: ld(f"lgbm_amt_{t}.txt") for t in TARGETS}
    try:
        calib = pickle.load(open(os.path.join(MODELS_FROM, "calibrators.pkl"), "rb"))
        calib = {t: calib[t] for t in TARGETS}
    except Exception as e:      # e.g. a different scikit-learn version: refit on the validation year (same result)
        print("Calibrators refitted on the validation year:", repr(e)[:80])
        calib = {t: IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
                    models[t].predict_proba(val[FEATURES])[:, 1], val[t]) for t in TARGETS}
    PARAMS = mm.get("params", PARAMS)
    print(f"Loaded {len(models)} models from {MODELS_FROM} (trained {mm.get('trained', '?')})")
else:
    if TUNE:
        # Random search on the validation year. Each trial trains the two main targets with a short patience;
        # the score is their mean validation log-loss. Test years are never touched.
        rs_ = np.random.default_rng(SEED)
        SPACE = {"num_leaves": [15, 31, 63, 127], "min_child_samples": [20, 40, 80, 150, 300],
                 "learning_rate": [0.02, 0.03, 0.05], "colsample_bytree": [0.4, 0.6, 0.8],
                 "subsample": [0.7, 0.8, 1.0], "reg_lambda": [0.0, 1.0, 5.0, 20.0], "min_split_gain": [0.0, 0.01]}
        TT = [t for t in ["bust_rain", "bust"] if t in TARGETS]
        def trial_score(prm):
            ls = []
            for t in TT:
                m, _ = train(FEATURES, t, calibrate=False, params=prm, patience=60)
                ls.append(m.best_score_["valid_0"]["binary_logloss"])
            return float(np.mean(ls))
        t0 = time.time(); trials = [(trial_score(PARAMS), dict(PARAMS))]
        print(f"  default settings: val log-loss {trials[0][0]:.4f}")
        for k in range(N_TRIALS):
            prm = dict(PARAMS, **{a: v[rs_.integers(len(v))] for a, v in SPACE.items()})
            prm["subsample_freq"] = 0 if prm["subsample"] == 1.0 else 1
            sc = trial_score(prm); trials.append((sc, prm))
            print(f"  trial {k + 1:2d}/{N_TRIALS}: log-loss {sc:.4f}  leaves={prm['num_leaves']} min_child={prm['min_child_samples']} "
                  f"lr={prm['learning_rate']} cols={prm['colsample_bytree']} l2={prm['reg_lambda']}  ({time.time() - t0:.0f}s)")
        best = min(trials, key=lambda x: x[0])
        print(f"Tuning: best val log-loss {best[0]:.4f} vs default {trials[0][0]:.4f}")
        PARAMS = best[1]
        json.dump({"best": PARAMS, "trials": [{"logloss": a, **b} for a, b in trials]}, open(f"{OUT}/tuning.json", "w"), indent=1, default=float)
    models, calib, v1_models, amt_models = {}, {}, {}, {}
    for t in TARGETS:
        models[t], calib[t] = train(FEATURES, t)
        v1_models[t], _ = train(V1_FEATURES, t, calibrate=False)
        amt_models[t], _ = train(BASE_FEATS, t, calibrate=False)
        print(f"{t:14s} trees={models[t].best_iteration_ or models[t].n_estimators:5d}  "
              f"val AUC={roc_auc_score(val[t], models[t].predict_proba(val[FEATURES])[:, 1]):.3f}")
for t in TARGETS:
    df["p_" + t] = calib[t].predict(models[t].predict_proba(df[FEATURES])[:, 1])

# %%
# ---- 7b. Rainfall ranges: "expect 12-48 mm/day (90% range)" ---------------------------------------
# Quantile models for the observed region-mean rain (5th, 50th, 95th percentile), then a conformal
# correction per lead day on the validation year, so the 90% range really covers ~90% of outcomes.
QPARAMS = dict(n_estimators=1500, learning_rate=0.05, num_leaves=31, min_child_samples=80, subsample=0.8,
               subsample_freq=1, colsample_bytree=0.7, random_state=SEED, verbose=-1)
rain_q = {}
for a_ in (0.05, 0.5, 0.95):
    if MODE == "infer":
        rain_q[a_] = Saved(os.path.join(MODELS_FROM, f"lgbm_rain_q{int(a_ * 100):02d}.txt")); continue
    m = lgb.LGBMRegressor(objective="quantile", alpha=a_, **QPARAMS)
    m.fit(fit[FEATURES], fit["obs_rain"], eval_set=[(val[FEATURES], val["obs_rain"])], eval_metric="quantile",
          callbacks=[lgb.early_stopping(100, verbose=False)])
    rain_q[a_] = m
def rain_range(frame):
    lo = rain_q[0.05].predict(frame[FEATURES]); md = rain_q[0.5].predict(frame[FEATURES]); hi = rain_q[0.95].predict(frame[FEATURES])
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    return np.clip(lo, 0, None), np.clip(md, 0, None), np.clip(hi, 0, None)
lo_v, _, hi_v = rain_range(val)
score = np.maximum(lo_v - val["obs_rain"].values, val["obs_rain"].values - hi_v)
RAIN_Q_ADJ = {}
for L in LEADS:
    sc = score[val["lead"].values == L]; n = len(sc)
    RAIN_Q_ADJ[int(L)] = float(np.quantile(sc, min(1.0, 0.90 * (1 + 1 / max(n, 1))))) if n else 0.0
lo_a, md_a, hi_a = rain_range(df)
adj = df["lead"].map(RAIN_Q_ADJ).values
df["rain_lo"], df["rain_med"], df["rain_hi"] = np.clip(lo_a - adj, 0, None), md_a, hi_a + adj
te_ = df[df.split == "test"]
cover = ((te_.obs_rain >= te_.rain_lo) & (te_.obs_rain <= te_.rain_hi))
rng_tab = pd.DataFrame({"coverage": cover.groupby(te_.lead).mean(),
                        "median_width_mm": (te_.rain_hi - te_.rain_lo).groupby(te_.lead).median()}).round(2)
print(f"Rainfall 90% range, test years: coverage {cover.mean():.1%} (target 90%)"); print(rng_tab.T.to_string())
rng_tab.to_csv(f"{OUT}/rain_range_coverage.csv")

# %%
# ---- 8. Scorecard on the held-out test years ---------------------------------------------------------
te = df[df.split == "test"]
rows = []
for t in TARGETS:
    if te[t].nunique() < 2: continue
    y, p_ = te[t].values, te["p_" + t].values
    base = (df[df.split.isin(["fit", "val"])].groupby(["region", "lead", "season"])[t].mean()
            .reindex(pd.MultiIndex.from_frame(te[["region", "lead", "season"]])).fillna(y.mean()).values)
    top = te.assign(p=p_).nlargest(max(1, len(te) // 10), "p")
    rows.append({"target": t, "bust_rate": y.mean(),
                 "AUC_BustRadar": roc_auc_score(y, p_),
                 "AUC_v1_features": roc_auc_score(y, v1_models[t].predict_proba(te[V1_FEATURES])[:, 1]) if v1_models.get(t) else np.nan,
                 "AUC_amount_only": roc_auc_score(y, amt_models[t].predict_proba(te[BASE_FEATS])[:, 1]) if amt_models.get(t) else np.nan,
                 "AUC_climatology": roc_auc_score(y, base),
                 "PR_AUC": average_precision_score(y, p_),
                 "Brier_skill_vs_clim": 1 - brier_score_loss(y, p_) / brier_score_loss(y, base),
                 "hit_rate_top10pct": top[t].mean()})
metrics = pd.DataFrame(rows).round(3)
print(metrics.to_string(index=False)); metrics.to_csv(f"{OUT}/metrics.csv", index=False)
by_lead = pd.DataFrame({t: te.groupby("lead").apply(lambda g: roc_auc_score(g[t], g["p_" + t]) if g[t].nunique() > 1 else np.nan)
                        for t in TARGETS}).round(3)
print("\nAUC by lead day (test):"); print(by_lead.T.to_string())
by_lead.to_csv(f"{OUT}/auc_by_lead.csv")

# Best alert threshold: chosen on the VALIDATION year (Peirce skill = hit rate - false-alarm rate, with a
# penalty so that alerts stay rare enough to be useful), then checked on the test years.
def pod_far(y, a):
    hits, miss, fa = (a & y).sum(), (~a & y).sum(), (a & ~y).sum(); cn = (~a & ~y).sum()
    return hits / max(hits + miss, 1), fa / max(fa + cn, 1), fa / max(hits + fa, 1)
thr_rows = []
yv, pv = val["bust"].values.astype(bool), df.loc[val.index, "p_bust"].values
for th in np.arange(0.30, 0.91, 0.05):
    pod, pofd, far = pod_far(yv, pv >= th)
    thr_rows.append({"threshold": round(th, 2), "hit_rate": pod, "false_alarm_rate": pofd, "false_alarm_ratio": far,
                     "peirce": pod - pofd, "alerts_per_100": 100 * (pv >= th).mean()})
thr_tab = pd.DataFrame(thr_rows)
ok = thr_tab[thr_tab.alerts_per_100 <= 15] if (thr_tab.alerts_per_100 <= 15).any() else thr_tab
ALERT_THR = float(ok.loc[ok.peirce.idxmax(), "threshold"])
yt, pt = te["bust"].values.astype(bool), te["p_bust"].values
pod, pofd, far = pod_far(yt, pt >= ALERT_THR)
print(f"\nAlert threshold chosen on validation: P(bust) >= {ALERT_THR:.0%}. Test years: hit rate {pod:.0%}, "
      f"false-alarm ratio {far:.0%}, {100 * (pt >= ALERT_THR).mean():.1f} alerts per 100 region-days")
thr_tab.round(3).to_csv(f"{OUT}/alert_thresholds.csv", index=False)

# %%
# ---- 9. Charts --------------------------------------------------------------------------------------
import matplotlib.pyplot as plt
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
COL = {"bust_rain": "#0070C0", "bust_heat": "#D64541", "bust_wind": "#7B4FA0", "bust_z500": "#2E9E5B",
       "bust": "#1F3864", "bust_rain_rel": "#E8772E"}
NICE = {"bust_rain": "Rain", "bust_heat": "Heat (Tmax)", "bust_wind": "Wind", "bust_z500": "500 hPa pattern",
        "bust": "Any", "bust_rain_rel": "Rain (relative)"}
fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))
bins = np.linspace(0, 1, 11)
for t in TARGETS:
    b = np.clip(np.digitize(te["p_" + t], bins) - 1, 0, 9)
    g = te.groupby(b).agg(p=("p_" + t, "mean"), o=(t, "mean"), n=(t, "size")); g = g[g.n >= 30]
    ax[0].plot(g.p, g.o, "-o", ms=3, color=COL[t], label=NICE[t])
ax[0].plot([0, 1], [0, 1], "--", color="grey", lw=1)
ax[0].set(title="Reliability (test years)", xlabel="Predicted bust probability", ylabel="Observed frequency", xlim=(0, 1), ylim=(0, 1))
ax[0].legend(frameon=False, fontsize=8)
for t in TARGETS:
    ax[1].plot(by_lead.index, by_lead[t], "-o", ms=3, color=COL[t], label=NICE[t])
ax[1].axhline(0.5, color="grey", ls="--", lw=1)
ax[1].set(title="Skill by lead day", xlabel="Lead day", ylabel="ROC-AUC", ylim=(0.45, 1))
x = np.arange(len(metrics)); wdt = 0.2
for k, (c, lab_, colr) in enumerate([("AUC_climatology", "Climatology", "#BFC7D3"), ("AUC_amount_only", "Amount only", "#8FA3BF"),
                                     ("AUC_v1_features", "v1 features", "#4F78A8"), ("AUC_BustRadar", "BustRadar", "#1F3864")]):
    ax[2].bar(x + (k - 1.5) * wdt, metrics[c], wdt, color=colr, label=lab_)
ax[2].set_xticks(x, [NICE[t] for t in metrics.target], rotation=20); ax[2].set_ylim(0.45, 1)
ax[2].set(title="What each layer adds (test AUC)"); ax[2].legend(frameon=False, fontsize=8, ncol=2)
plt.tight_layout(); plt.savefig(f"{OUT}/fig_scorecard.png"); plt.show()

imp = pd.Series(models["bust"].booster_.feature_importance("gain"), index=FEATURES).sort_values().tail(20)
fig, ax = plt.subplots(figsize=(7, 6)); ax.barh(imp.index, imp.values, color="#E8772E")
ax.set(title="Top drivers of bust risk (any bust, gain)"); plt.tight_layout(); plt.savefig(f"{OUT}/fig_importance.png"); plt.show()

# %%
# ---- 10. Which weather systems make forecasts bust? ----------------------------------------------------
sys_rows = []
alld = df[df.split.isin(["fit", "val", "test"])]
for s in [c for c in df.columns if c.startswith("sys_")]:
    on = alld[alld[s] == 1]
    if len(on) < 30: continue
    for t in [x for x in ["bust_rain", "bust_heat", "bust_wind", "bust_z500", "bust"] if x in df]:
        base = alld.loc[alld[s] == 0, t].mean()
        sys_rows.append({"system": s.replace("sys_", ""), "target": t, "cases": len(on),
                         "bust_rate": on[t].mean(), "bust_rate_otherwise": base, "times_more_likely": on[t].mean() / max(base, 1e-6)})
if "obs_monsoon_phase" in df:
    jj = alld[alld.obs_monsoon_phase.isin(["active", "break", "normal"])]
    for ph, g in jj.groupby("obs_monsoon_phase"):
        sys_rows.append({"system": f"observed {ph} monsoon", "target": "bust_rain", "cases": len(g),
                         "bust_rate": g.bust_rain.mean(), "bust_rate_otherwise": jj.bust_rain.mean(),
                         "times_more_likely": g.bust_rain.mean() / max(jj.bust_rain.mean(), 1e-6)})
sysdf = pd.DataFrame(sys_rows).round(3)
print(sysdf.to_string(index=False)); sysdf.to_csv(f"{OUT}/busts_by_system.csv", index=False)
if len(sysdf):
    s1 = sysdf[sysdf.target.isin(["bust", "bust_rain"])].sort_values("times_more_likely")
    s1 = s1.drop_duplicates("system", keep="last")
    s1 = s1.assign(label=s1.system + "  →  " + s1.target.map(NICE) + " busts")
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(s1) + 1.2))
    ax.barh(s1.label, s1.times_more_likely, color=["#D64541" if v > 1 else "#2E9E5B" for v in s1.times_more_likely])
    ax.axvline(1, color="grey", ls="--", lw=1)
    ax.set(title="How much more likely is a forecast bust?", xlabel="× the usual bust rate")
    plt.tight_layout(); plt.savefig(f"{OUT}/fig_busts_by_system.png"); plt.show()

# %%
# ---- 11. Explanations: SHAP -> plain-language reasons that name the weather system --------------------
R_ = {   # feature -> (group, text)
    "sys_depression": ("system", lambda r: f"Monsoon depression/low in the forecast ({min(r.get('bay_low_anom', 0), r.get('central_low_anom', 0)):+.0f} hPa vs normal)"),
    "sys_cyclone": ("system", lambda r: f"Cyclonic system over the sea (pressure {r.get('sea_low_anom', 0):+.0f} hPa, winds {r.get('sea_wind_max', 0):.0f} m/s)"),
    "sys_wd": ("system", lambda r: f"Western disturbance: upper trough over the northwest ({r.get('wd_trough_anom', 0):+.0f} m at 500 hPa)"),
    "sys_heatwave": ("system", lambda r: f"Heat wave in the forecast (Tmax {r.get('fc_tmax_bc', 273.15) - 273.15:.0f} °C)"),
    "sys_active": ("system", lambda r: "Active monsoon spell forecast"),
    "sys_break": ("system", lambda r: "Break in the monsoon forecast"),
    "phase_change_fc": ("system", lambda r: f"Monsoon phase change expected (active/break transition, {r.phase_change_fc:+.1f} σ)"),
    "lag_spread_rain": ("spread", lambda r: "Recent model runs disagree on the rain for this day"),
    "lag_spread_z500": ("spread", lambda r: "Recent runs disagree on the large-scale pattern"),
    "lag_spread_mslp": ("spread", lambda r: "Recent runs disagree on surface pressure (low position/strength)"),
    "lag_spread_tmax": ("spread", lambda r: "Recent runs disagree on the maximum temperature"),
    "lag_spread_wind10max": ("spread", lambda r: "Recent runs disagree on wind strength"),
    "rain_patcorr": ("spread", lambda r: f"Rain pattern changed between runs (agreement {r.rain_patcorr:.2f})"),
    "india_z500_patcorr": ("spread", lambda r: f"Large-scale pattern changed between runs (agreement {r.india_z500_patcorr:.2f})"),
    "jump_rain_abs": ("jump", lambda r: f"Rain forecast changed by {r.jump_rain:+.1f} mm/day since yesterday's run"),
    "jump_mslp_abs": ("jump", lambda r: f"Surface pressure forecast changed {r.jump_mslp:+.1f} hPa between runs"),
    "jump_z500_abs": ("jump", lambda r: f"500 hPa height jumped {r.jump_z500:+.0f} m between runs"),
    "jump_tmax_abs": ("jump", lambda r: f"Max temperature forecast changed {r.jump_tmax:+.1f} K between runs"),
    "vort850": ("dyn", lambda r: f"Strong low-level spin ({r.vort850:.1f}×10⁻⁵ s⁻¹): a low-pressure system"),
    "vort850_max": ("dyn", lambda r: "Intense low-level circulation nearby"),
    "mfc850": ("moist", lambda r: f"Strong moisture convergence ({r.mfc850:+.1f})"),
    "ivt850": ("moist", lambda r: "Strong moisture transport into the region"),
    "fc_q700_anom": ("moist", lambda r: f"Unusually {'moist' if r.fc_q700_anom > 0 else 'dry'} mid-levels ({r.fc_q700_anom:+.1f} g/kg)"),
    "k_index": ("instab", lambda r: f"Unstable atmosphere (K-index {r.k_index:.0f})"),
    "lapse850_500": ("instab", lambda r: f"Steep lapse rate ({r.lapse850_500:.0f} K between 850 and 500 hPa)"),
    "ascent500": ("dyn", lambda r: "Strong rising motion at mid-levels"),
    "shear200_850": ("dyn", lambda r: f"Strong wind shear ({r.shear200_850:.0f} m/s, 200–850 hPa)"),
    "jet200": ("dyn", lambda r: f"Strong upper-level jet ({r.jet200:.0f} m/s)"),
    "wd_jet_max": ("dyn", lambda r: f"Subtropical jet over the northwest ({r.wd_jet_max:.0f} m/s)"),
    "monsoon_trough_lat": ("system", lambda r: f"Monsoon trough near {r.monsoon_trough_lat:.0f}°N"),
    "fc_rain": ("amount", lambda r: f"Heavy rain forecast ({r.fc_rain:.0f} mm/day region mean)"),
    "fc_rain_max": ("amount", lambda r: f"Intense local rain forecast (peak {r.fc_rain_max:.0f} mm/day)"),
    "fc_rain_anom": ("amount", lambda r: f"Rain forecast far from normal ({r.fc_rain_anom:+.0f} mm/day)"),
    "rain_cv": ("amount", lambda r: "Patchy, concentrated rain: hard to place exactly"),
    "fc_wind10max_max": ("amount", lambda r: f"Strong winds forecast (up to {r.fc_wind10max_max:.0f} m/s)"),
    "fc_tmax_anom": ("amount", lambda r: f"Max temperature far from normal ({r.fc_tmax_anom:+.1f} K)"),
    "fc_z500_anom": ("pattern", lambda r: f"{'Trough' if r.fc_z500_anom < 0 else 'Ridge'} at 500 hPa ({r.fc_z500_anom:+.0f} m)"),
    "fc_mslp_anom": ("pattern", lambda r: f"{'Low' if r.fc_mslp_anom < 0 else 'High'} surface pressure ({r.fc_mslp_anom:+.1f} hPa)"),
    "analog_bust_rate": ("analog", lambda r: f"{r.analog_bust_rate:.0%} of the most similar past forecasts busted here"),
    "analog_rain_bust_rate": ("analog", lambda r: f"{r.analog_rain_bust_rate:.0%} of similar past forecasts had rain busts here"),
    "recent_rain_rmse": ("memory", lambda r: f"Model has struggled here in the last 3 days ({r.recent_rain_rmse:.1f} mm/day error)"),
    "week_rain_rmse": ("memory", lambda r: "Model has struggled here all week"),
    "rain_err_trend": ("memory", lambda r: "Recent errors are getting worse"),
    "week_rain_anom": ("memory", lambda r: f"Unusually {'wet' if r.week_rain_anom > 0 else 'dry'} past week ({r.week_rain_anom:+.0f} mm/day)"),
    "mjo_amp": ("climate", lambda r: f"Strong MJO pulse (amplitude {r.mjo_amp:.1f})"),
    "nino34": ("climate", lambda r: f"{'El Niño' if r.nino34 > 0 else 'La Niña'} background ({r.nino34:+.1f} °C)"),
    "iod_dmi": ("climate", lambda r: f"{'Positive' if r.iod_dmi > 0 else 'Negative'} Indian Ocean Dipole ({r.iod_dmi:+.2f})"),
    "nbr_jump_rain_abs": ("nbr", lambda r: "Forecasts for neighbouring regions are also unstable"),
    "nbr_lag_spread_rain": ("nbr", lambda r: "Neighbouring regions also show run-to-run disagreement"),
    "lead": ("lead", lambda r: f"Long lead time (Day {int(r.lead)})"),
    "doy_sin": ("season", lambda r: "Historically error-prone time of year"),
    "doy_cos": ("season", lambda r: "Historically error-prone time of year"),
}
sg = lambda v, pos, neg: pos if v > 0 else neg
R_HI = {   # Hindi versions of the same reasons (numbers and units unchanged)
    "sys_depression": lambda r: f"पूर्वानुमान में मानसून अवदाब / निम्न दबाव (सामान्य से {min(r.get('bay_low_anom', 0), r.get('central_low_anom', 0)):+.0f} hPa)",
    "sys_cyclone": lambda r: f"समुद्र पर चक्रवाती प्रणाली (दबाव {r.get('sea_low_anom', 0):+.0f} hPa, हवाएँ {r.get('sea_wind_max', 0):.0f} m/s)",
    "sys_wd": lambda r: f"पश्चिमी विक्षोभ: उत्तर-पश्चिम पर ऊपरी गर्त (500 hPa पर {r.get('wd_trough_anom', 0):+.0f} m)",
    "sys_heatwave": lambda r: f"पूर्वानुमान में लू (अधिकतम तापमान {r.get('fc_tmax_bc', 273.15) - 273.15:.0f} °C)",
    "sys_active": lambda r: "मानसून की सक्रिय अवस्था का पूर्वानुमान",
    "sys_break": lambda r: "मानसून में विराम (ब्रेक) का पूर्वानुमान",
    "phase_change_fc": lambda r: f"मानसून अवस्था में बदलाव की संभावना (सक्रिय/विराम, {r.phase_change_fc:+.1f} σ)",
    "lag_spread_rain": lambda r: "हाल के मॉडल रन इस दिन की वर्षा पर असहमत हैं",
    "lag_spread_z500": lambda r: "हाल के रन बड़े पैमाने के पैटर्न पर असहमत हैं",
    "lag_spread_mslp": lambda r: "हाल के रन सतही दबाव (निम्न दबाव की स्थिति/तीव्रता) पर असहमत हैं",
    "lag_spread_tmax": lambda r: "हाल के रन अधिकतम तापमान पर असहमत हैं",
    "lag_spread_wind10max": lambda r: "हाल के रन हवा की तीव्रता पर असहमत हैं",
    "rain_patcorr": lambda r: f"रनों के बीच वर्षा का पैटर्न बदल गया (मेल {r.rain_patcorr:.2f})",
    "india_z500_patcorr": lambda r: f"रनों के बीच बड़े पैमाने का पैटर्न बदल गया (मेल {r.india_z500_patcorr:.2f})",
    "jump_rain_abs": lambda r: f"कल के रन से वर्षा पूर्वानुमान {r.jump_rain:+.1f} mm/दिन बदला",
    "jump_mslp_abs": lambda r: f"रनों के बीच सतही दबाव पूर्वानुमान {r.jump_mslp:+.1f} hPa बदला",
    "jump_z500_abs": lambda r: f"रनों के बीच 500 hPa ऊँचाई {r.jump_z500:+.0f} m बदली",
    "jump_tmax_abs": lambda r: f"रनों के बीच अधिकतम तापमान पूर्वानुमान {r.jump_tmax:+.1f} K बदला",
    "vort850": lambda r: f"निचले स्तर पर प्रबल चक्रण ({r.vort850:.1f}×10⁻⁵ s⁻¹): निम्न दबाव प्रणाली",
    "vort850_max": lambda r: "पास में तीव्र निम्न-स्तरीय परिसंचरण",
    "mfc850": lambda r: f"प्रबल नमी अभिसरण ({r.mfc850:+.1f})",
    "ivt850": lambda r: "क्षेत्र में प्रबल नमी परिवहन",
    "fc_q700_anom": lambda r: f"मध्य स्तर असामान्य रूप से {sg(r.fc_q700_anom, 'नम', 'शुष्क')} ({r.fc_q700_anom:+.1f} g/kg)",
    "k_index": lambda r: f"अस्थिर वायुमंडल (K-सूचकांक {r.k_index:.0f})",
    "lapse850_500": lambda r: f"तीव्र ताप-ह्रास दर (850 और 500 hPa के बीच {r.lapse850_500:.0f} K)",
    "ascent500": lambda r: "मध्य स्तर पर प्रबल ऊर्ध्वगामी वायु",
    "shear200_850": lambda r: f"प्रबल पवन अपरूपण ({r.shear200_850:.0f} m/s, 200–850 hPa)",
    "jet200": lambda r: f"प्रबल ऊपरी जेट ({r.jet200:.0f} m/s)",
    "wd_jet_max": lambda r: f"उत्तर-पश्चिम पर उपोष्णकटिबंधीय जेट ({r.wd_jet_max:.0f} m/s)",
    "monsoon_trough_lat": lambda r: f"मानसून द्रोणी लगभग {r.monsoon_trough_lat:.0f}° उत्तर पर",
    "fc_rain": lambda r: f"भारी वर्षा का पूर्वानुमान (क्षेत्रीय औसत {r.fc_rain:.0f} mm/दिन)",
    "fc_rain_max": lambda r: f"स्थानीय तीव्र वर्षा का पूर्वानुमान (अधिकतम {r.fc_rain_max:.0f} mm/दिन)",
    "fc_rain_anom": lambda r: f"वर्षा पूर्वानुमान सामान्य से बहुत अलग ({r.fc_rain_anom:+.0f} mm/दिन)",
    "rain_cv": lambda r: "बिखरी, केंद्रित वर्षा: सटीक स्थान बताना कठिन",
    "fc_wind10max_max": lambda r: f"तेज़ हवाओं का पूर्वानुमान ({r.fc_wind10max_max:.0f} m/s तक)",
    "fc_tmax_anom": lambda r: f"अधिकतम तापमान सामान्य से बहुत अलग ({r.fc_tmax_anom:+.1f} K)",
    "fc_z500_anom": lambda r: f"500 hPa पर {sg(-r.fc_z500_anom, 'गर्त', 'कटक')} ({r.fc_z500_anom:+.0f} m)",
    "fc_mslp_anom": lambda r: f"सतही दबाव सामान्य से {sg(-r.fc_mslp_anom, 'कम', 'अधिक')} ({r.fc_mslp_anom:+.1f} hPa)",
    "analog_bust_rate": lambda r: f"सबसे मिलते-जुलते पिछले पूर्वानुमानों में से {r.analog_bust_rate:.0%} यहाँ विफल रहे",
    "analog_rain_bust_rate": lambda r: f"मिलते-जुलते पिछले पूर्वानुमानों में से {r.analog_rain_bust_rate:.0%} में यहाँ वर्षा-त्रुटि रही",
    "recent_rain_rmse": lambda r: f"पिछले 3 दिनों में यहाँ मॉडल की त्रुटि अधिक रही ({r.recent_rain_rmse:.1f} mm/दिन)",
    "week_rain_rmse": lambda r: "पूरे सप्ताह यहाँ मॉडल की त्रुटि अधिक रही",
    "rain_err_trend": lambda r: "हाल की त्रुटियाँ बढ़ रही हैं",
    "week_rain_anom": lambda r: f"पिछला सप्ताह असामान्य रूप से {sg(r.week_rain_anom, 'गीला', 'सूखा')} रहा ({r.week_rain_anom:+.0f} mm/दिन)",
    "mjo_amp": lambda r: f"प्रबल MJO स्पंद (आयाम {r.mjo_amp:.1f})",
    "nino34": lambda r: f"{sg(r.nino34, 'एल नीनो', 'ला नीना')} पृष्ठभूमि ({r.nino34:+.1f} °C)",
    "iod_dmi": lambda r: f"{sg(r.iod_dmi, 'धनात्मक', 'ऋणात्मक')} हिंद महासागर द्विध्रुव ({r.iod_dmi:+.2f})",
    "nbr_jump_rain_abs": lambda r: "पड़ोसी क्षेत्रों के पूर्वानुमान भी अस्थिर हैं",
    "nbr_lag_spread_rain": lambda r: "पड़ोसी क्षेत्रों में भी रनों के बीच असहमति है",
    "lead": lambda r: f"लंबी अग्रिम अवधि (दिन {int(r.lead)})",
    "doy_sin": lambda r: "वर्ष का वह समय जब त्रुटियाँ ऐतिहासिक रूप से अधिक होती हैं",
    "doy_cos": lambda r: "वर्ष का वह समय जब त्रुटियाँ ऐतिहासिक रूप से अधिक होती हैं",
}
tr_ = df[df.split.isin(["fit", "val"])]
NOTABLE = {f: tr_[f].abs().quantile(0.6) for f in R_ if f in tr_ and not f.startswith(("sys_", "lead", "doy"))}
# smallest value worth saying out loud (so no "+0 mm/day" reasons)
MIN_ABS = {"jump_rain_abs": 3.0, "jump_mslp_abs": 1.0, "jump_z500_abs": 10.0, "jump_tmax_abs": 1.0, "fc_rain": 10.0,
           "fc_rain_max": 20.0, "fc_rain_anom": 5.0, "fc_q700_anom": 0.5, "fc_z500_anom": 20.0, "fc_mslp_anom": 2.0,
           "fc_tmax_anom": 2.0, "fc_wind10max_max": 10.0, "week_rain_anom": 3.0, "recent_rain_rmse": 3.0,
           "week_rain_rmse": 3.0, "rain_err_trend": 1.0, "vort850": 1.0, "mfc850": 0.5, "mjo_amp": 1.0,
           "nino34": 0.5, "iod_dmi": 0.4, "analog_bust_rate": 0.3, "analog_rain_bust_rate": 0.3, "phase_change_fc": 1.0,
           "lapse850_500": 26.0, "k_index": 30.0, "shear200_850": 20.0, "jet200": 30.0}
NOTABLE = {f: max(v, MIN_ABS.get(f, 0.0)) for f, v in NOTABLE.items()}
LOW_IS_BAD = {"rain_patcorr", "india_z500_patcorr"}
def notable(f, r):
    v = r.get(f, np.nan)
    if f == "lead": return r.lead >= 5
    if f.startswith("sys_"): return v == 1
    if f.startswith("doy"): return True
    if pd.isna(v): return False
    if f in LOW_IS_BAD: return v < 0.6
    if f in ("vort850", "vort850_max", "mfc850", "ascent500") and v <= 0: return False   # only cyclonic spin / convergence / ascent
    if f in ("phase_change_fc", "monsoon_trough_lat") and r.valid_date.month not in (6, 7, 8, 9): return False
    return abs(v) > NOTABLE.get(f, 0)
# Explanations only where they are used: risky forecasts (P >= 25%) in the validation/test years shown on the dashboard.
# (Exact SHAP for every row of every year would take hours on a CPU.)
TYPE_COLS = [t for t in ["bust_rain", "bust_heat", "bust_wind", "bust_z500"] if t in TARGETS]
df["main_risk"] = df[["p_" + t for t in TYPE_COLS]].idxmax(axis=1).str.replace("p_bust_", "", regex=False)
need = df.index[(df["p_bust"] >= 0.25) & df["split"].isin(["val", "test", "live"])]
t0 = time.time()
parts = []
for t in TYPE_COLS:                      # explain each forecast with the model of its most likely bust type
    ix = need[df.loc[need, "main_risk"].values == t.replace("bust_", "")]
    if len(ix):
        parts.append(pd.DataFrame(models[t].predict(df.loc[ix, FEATURES], pred_contrib=True)[:, :-1], columns=FEATURES, index=ix))
contrib = pd.concat(parts).reindex(need) if parts else pd.DataFrame(columns=FEATURES)
print(f"SHAP for {len(need)} risky forecasts in {time.time() - t0:.0f}s")
RAIN_ONLY = {"fc_rain", "fc_rain_max", "fc_rain_anom", "rain_cv", "lag_spread_rain", "rain_patcorr", "jump_rain_abs",
             "analog_rain_bust_rate", "recent_rain_rmse", "week_rain_rmse", "rain_err_trend", "nbr_jump_rain_abs",
             "nbr_lag_spread_rain", "sys_active", "sys_break", "phase_change_fc", "week_rain_anom"}
def fits(f, risk):
    """Keep reasons that make sense for the kind of bust expected."""
    heatish = "tmax" in f or f == "sys_heatwave"
    if risk != "heat" and heatish: return False
    if risk == "heat" and f in RAIN_ONLY: return False
    return True
def reasons_for(i, k=3):
    r, c = df.loc[i], contrib.loc[i]; out, used = [], set()
    for f in c.sort_values(ascending=False).index:
        if c[f] <= 0 or len(out) >= k: break
        if f not in R_ or not notable(f, r) or not fits(f, r.main_risk): continue
        g, fn = R_[f]
        if g in used: continue
        try:
            en = fn(r)
            try: hi = R_HI[f](r) if f in R_HI else en
            except Exception: hi = en
            out.append((en, hi)); used.add(g)
        except Exception: pass
    return out
df["reasons"], df["reasons_hi"] = "", ""
_rs = [reasons_for(i) for i in need]
df.loc[need, "reasons"] = [" | ".join(e for e, _ in x) for x in _rs]
df.loc[need, "reasons_hi"] = [" | ".join(h for _, h in x) for x in _rs]
print(f"Reasons written in {time.time() - t0:.0f}s")
df["confidence"] = (100 * (1 - df["p_bust"])).round().astype(int)
for _, r in df[df.split == "test"].nlargest(6, "p_bust").iterrows():
    print(f"{r.region:13s} {r.init.date()} Day {r.lead:2d}  P(bust)={r.p_bust:.2f} [{r.main_risk}] actual={r.bust}\n   -> {r.reasons}")

# %%
# ---- 12. Event replay --------------------------------------------------------------------------------
EVENTS = [  # name, region, start, end, which bust type matters most
    ("Kerala floods", "West Coast", "2018-08-14", "2018-08-17", "bust_rain"),
    ("Cyclone Fani", "East India", "2019-05-02", "2019-05-04", "bust"),
    ("Mumbai extreme rain", "West Coast", "2019-07-01", "2019-07-02", "bust_rain"),
    ("Cyclone Amphan", "East India", "2020-05-19", "2020-05-21", "bust"),
    ("Hyderabad floods", "S. Peninsula", "2020-10-13", "2020-10-14", "bust_rain"),
    ("Cyclone Tauktae", "West Coast", "2021-05-15", "2021-05-17", "bust"),
    ("Uttarakhand extreme rain", "Himalayan WH", "2021-10-17", "2021-10-19", "bust_rain"),
    ("NW India heat wave", "NW India", "2022-04-26", "2022-04-30", "bust_heat"),
    ("Assam/Meghalaya floods", "NE India", "2022-06-14", "2022-06-17", "bust_rain"),
]
rep = []
for name, region, d0, d1_, tgt in EVENTS:
    if tgt not in df: tgt = "bust"
    s = df[(df.region == region) & (df.valid_date >= d0) & (df.valid_date <= d1_)]
    if s.empty: continue
    g = s.groupby("lead").agg(p=("p_" + tgt, "max"), a=(tgt, "max"))
    sysf = [c.replace("sys_", "") for c in df.columns if c.startswith("sys_") and s[c].max() == 1]
    rep.append({"event": name, "region": region, "type": NICE[tgt], "split": s.split.iloc[0],
                **{f"D{L}": f"{g.p.get(L, np.nan):.2f}{'*' if g.a.get(L, 0) else ''}" for L in LEADS},
                "systems_detected": ",".join(sysf)})
rep = pd.DataFrame(rep)
print("P(bust) by lead day; * = the forecast really busted. Test-year events are the honest ones.")
print(rep.to_string(index=False) if len(rep) else "No events in range.")
rep.to_csv(f"{OUT}/event_replay.csv", index=False)

# %%
# ---- 13. Save for the dashboard -------------------------------------------------------------------------
def save_table(d, path):
    try: d.to_parquet(path, index=False)
    except Exception:
        path = path.replace(".parquet", ".csv.gz"); d.to_csv(path, index=False)
    print("saved", path, d.shape)

keep = (["init", "valid_date", "lead", "region", "split", "season", "confidence", "main_risk", "reasons", "reasons_hi"]
        + ["p_" + t for t in TARGETS] + TARGETS
        + [c for c in df.columns if c.startswith("sys_")]
        + [c for c in ["obs_monsoon_phase", "analog_bust_rate", "fc_rain", "fc_rain_max", "obs_rain", "rain_rmse",
                       "fc_tmax_bc", "obs_heat", "fc_wind10max_max", "obs_wind", "lag_spread_rain", "jump_rain",
                       "rain_lo", "rain_med", "rain_hi"] if c in df])
out_tab = df[list(dict.fromkeys(keep))].copy()
out_tab.loc[~VERIFIED, [c for c in TARGETS + ["obs_rain", "obs_heat", "obs_wind", "rain_rmse"] if c in out_tab]] = np.nan   # live: not verified yet
save_table(out_tab, f"{OUT}/predictions.parquet")
if MODE == "train" or os.path.abspath(MODELS_FROM) != os.path.abspath(OUT):
    for name, group in [("lgbm", models), ("lgbm_v1", v1_models), ("lgbm_amt", amt_models)]:
        for t, m in group.items():
            if m is not None: m.booster_.save_model(f"{OUT}/{name}_{t}.txt")
    pickle.dump(calib, open(f"{OUT}/calibrators.pkl", "wb"))
    for a_, m in rain_q.items():
        m.booster_.save_model(f"{OUT}/lgbm_rain_q{int(a_ * 100):02d}.txt")
    json.dump({"features": FEATURES, "v1_features": V1_FEATURES, "base_features": BASE_FEATS, "targets": TARGETS,
               "regions": REGION_NAMES, "type_labels": NICE, "params": PARAMS, "trained": time.strftime("%Y-%m-%d %H:%M"),
               "fit_years": FIT_YEARS, "val_years": VAL_YEARS, "test_years": TEST_YEARS},
              open(f"{OUT}/model_meta.json", "w"), indent=1, default=float)
json.dump(RAIN_Q_ADJ, open(f"{OUT}/rain_range_adjust.json", "w"))
json.dump({"alert_threshold": ALERT_THR, "mode": MODE, "run": time.strftime("%Y-%m-%d %H:%M"),
           "live_runs": sorted(df.loc[df.split == "live", "init"].dt.date.astype(str).unique().tolist())},
          open(f"{OUT}/run_info.json", "w"), indent=1)
json.dump({f"{k[0]}|{k[1]}": v for k, v in analog_dates.items()}, open(f"{OUT}/analog_dates.json", "w"))
tidx = df.index[(df.split == "test") & (df.p_bust >= 0.25)]
save_table(pd.concat([df.loc[tidx, ["init", "lead", "region"]], contrib.loc[tidx].round(4)], axis=1), f"{OUT}/shap_test.parquet")
shutil.copy(os.path.join(DATA, "grid_meta.nc"), f"{OUT}/grid_meta.nc")
print("Zip:", shutil.make_archive(OUT, "zip", OUT))
