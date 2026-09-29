# %% [markdown]
# # BustRadar — Day 1: Data pipeline (WeatherBench 2 + IMD)
#
# **What this notebook does**
# 1. Opens WeatherBench 2 (free, public Google Cloud bucket), with ECMWF IFS HRES forecasts + ERA5 at 1.5°
# 2. Downloads IMD 0.25° gridded rainfall (via `imdlib`) and converts it to the same 1.5° grid
# 3. Crops everything to India, for lead days 1–10, from 00 UTC runs
# 4. Computes forecast errors per **region × lead day**, and labels **forecast busts**
# 5. Saves small, clean files for the next steps (LightGBM, U-Net, dashboard)
#
# **Kaggle setup:** Settings → *Internet* **ON**. No GPU needed for this notebook.
# Run cells top to bottom. The download step is **resumable**: if the session dies, just re-run and it skips finished years.
#
# **Outputs** (in `/kaggle/working/bustradar_data/`, downloaded at the end as one zip):
# | file | what |
# |---|---|
# | `grid_meta.nc` | lat/lon, land mask, region id per grid cell |
# | `maps/fc_YYYY.nc` | India forecast maps: init × lead × lat × lon (rain, t2m, z500, winds…) → U-Net input |
# | `maps/obs_YYYY.nc` | observed maps on the same grid (IMD rain, ERA5 t2m) → U-Net target |
# | `regions.parquet` | one row per init × lead × region, with forecast, observation, errors, run-to-run jumps and bust labels |
# | `thresholds.csv` | bust thresholds per region × lead × season |
# | `fig_*.png` | first charts for the team and the pitch |

# %%
# ---- 1. Install ---------------------------------------------------------------
import os, sys, subprocess
ON_KAGGLE = os.path.exists("/kaggle")
if ON_KAGGLE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gcsfs", "zarr", "imdlib"], check=False)

# %%
# ---- 2. Config -----------------------------------------------------------------
import json, time, warnings, glob, shutil
import numpy as np
import pandas as pd
import xarray as xr
warnings.filterwarnings("ignore")

MOCK = globals().get("MOCK", False)          # True = offline test with synthetic data (leave False on Kaggle)

YEARS       = list(range(2016, 2023))        # WB2 HRES covers 2016-2022 (confirmed in cell 3)
TRAIN_YEARS = list(range(2016, 2021))        # thresholds + training
TEST_YEARS  = [2021, 2022]                   # held out, used for evaluation and replays
LEADS       = list(range(1, 11))             # Day 1 .. Day 10

# Full 2016-2022 run by default. Set QUICK_TEST = True only for a 1-year trial (2020).
# Finished years are skipped automatically, so switching back to False later just adds the missing years.
QUICK_TEST = False
if QUICK_TEST:
    YEARS, TRAIN_YEARS, TEST_YEARS = [2020], [2020], []

# India box on the WB2 1.5° grid (24 × 24 cells, handy for the U-Net)
RES = 1.5
LAT_MIN, LAT_MAX = 6.0, 40.5
LON_MIN, LON_MAX = 66.0, 100.5

OUT = "/kaggle/working/bustradar_data" if ON_KAGGLE else "./bustradar_data"
os.makedirs(f"{OUT}/maps", exist_ok=True)

# Leave None to auto-discover. Set a path string to override.
HRES_PATH = None
ERA5_PATH = None

# Download budget: variables whose estimated read size exceeds this are skipped (see cell 4)
DOWNLOAD_BUDGET_GB = 100       # for the FULL 2016-2022 run (uncompressed estimate; real transfer is smaller)
FULL_YEARS = list(range(2016, 2023))   # budget is always checked for the full run, so quick test = same variables

# Upper-air fields in the 1.5° store cost ~26 GB/year each (all 13 levels are stored together).
# We take them from WB2's coarse 5.6° copy (~14x smaller) and interpolate to 1.5°.
# That is fine for large-scale patterns: troughs, western disturbances, monsoon flow, moisture.
UPPER_AIR = {"z500", "u850", "v850", "q700"}
UPPER_AIR_FROM_COARSE = True
HRES_COARSE_PATH = None

# output name -> (WB2 variable, pressure level or None, timing)
#   'rain'  : 24 h accumulation over forecast day L  (lead 24(L-1)h .. 24L h)
#   'day12' : value at 12 UTC of forecast day L      (lead 24L-12 h)
#   'day00' : value at the end of forecast day L     (lead 24L h)
FC_VARS = {
    "rain": ("total_precipitation_24hr", None, "rain"),
    "t2m":  ("2m_temperature",           None, "day12"),
    "mslp": ("mean_sea_level_pressure",  None, "day00"),
    "z500": ("geopotential",             500,  "day00"),
    "u850": ("u_component_of_wind",      850,  "day00"),
    "v850": ("v_component_of_wind",      850,  "day00"),
    "q700": ("specific_humidity",        700,  "day00"),
}

# Regions as lat/lon boxes (lat_min, lat_max, lon_min, lon_max).
# Order = priority: a grid cell goes to the first region whose box contains it.
REGIONS = {
    "Himalayan WH":  [(29.0, 37.5, 72.5, 81.0)],
    "NE India":      [(21.5, 29.5, 89.5, 97.5)],
    "NW India":      [(23.5, 31.0, 68.0, 79.0), (20.0, 24.5, 68.0, 74.5)],
    "East India":    [(19.5, 27.5, 82.5, 89.5)],
    "West Coast":    [(8.0, 20.5, 72.0, 75.5)],
    "Central India": [(18.5, 26.0, 74.0, 84.0)],
    "S. Peninsula":  [(7.5, 19.0, 75.0, 85.0)],
}
REGION_NAMES = list(REGIONS)

# Famous events for the "Bust Replay" sanity check (dates = observed event days)
EVENTS = [
    ("Kerala floods",            "West Coast",    "2018-08-14", "2018-08-17", "rain"),
    ("Cyclone Fani (Odisha)",    "East India",    "2019-05-02", "2019-05-04", "rain"),
    ("Mumbai extreme rain",      "West Coast",    "2019-07-01", "2019-07-02", "rain"),
    ("Cyclone Amphan",           "East India",    "2020-05-19", "2020-05-21", "rain"),
    ("Hyderabad floods",         "S. Peninsula",  "2020-10-13", "2020-10-14", "rain"),
    ("Cyclone Tauktae",          "West Coast",    "2021-05-15", "2021-05-17", "rain"),
    ("Uttarakhand extreme rain", "Himalayan WH",  "2021-10-17", "2021-10-19", "rain"),
    ("NW India heat wave",       "NW India",      "2022-04-26", "2022-04-30", "t2m"),
    ("Assam/Meghalaya floods",   "NE India",      "2022-06-14", "2022-06-17", "rain"),
]

# Bust definition: error above the 90th percentile of its own region × lead × season (training years),
# and above a small absolute floor so tiny dry-season errors never count as busts.
BUST_Q = 0.90
FLOOR = {"rain_rmse": 5.0, "t2m_abs": 1.5}   # mm/day, K

def save_table(df, path):
    try:
        df.to_parquet(path, index=False)
    except Exception:                          # no pyarrow (offline test only)
        path = path.replace(".parquet", ".csv.gz"); df.to_csv(path, index=False)
    print("saved", path, df.shape)
    return path

print("Output folder:", OUT, "| MOCK =", MOCK)

# %%
# ---- 3. Open WeatherBench 2 (auto-discover the 1.5° stores) ----------------------
def discover(fs, prefix, must, prefer=()):
    items = [p for p in fs.ls(prefix) if p.endswith(".zarr")]
    print(f"\n{prefix}  ({len(items)} stores)")
    for p in items: print("   ", p.split("/")[-1])
    cands = [p for p in items if all(m in p for m in must)]
    for pref in prefer:
        c2 = [p for p in cands if pref in p]
        if c2: cands = c2
    if not cands:
        raise RuntimeError(f"No store in {prefix} matches {must}. Set the path manually in cell 2.")
    return "gs://" + sorted(cands)[0]

if MOCK:
    hres, era5 = make_mock_wb2()               # defined in the offline test harness
    hres_c = hres.isel(latitude=slice(None, None, 3), longitude=slice(None, None, 3))
else:
    import gcsfs
    fs = gcsfs.GCSFileSystem(token="anon")
    HRES_PATH = HRES_PATH or discover(fs, "weatherbench2/datasets/hres", ["240x121", "with_poles"], prefer=["0012"])
    HRES_COARSE_PATH = HRES_COARSE_PATH or discover(fs, "weatherbench2/datasets/hres", ["64x32"], prefer=["0012"])
    # the "2023_01_10" copy runs to Jan 2023, so 2022 forecasts also have ERA5 truth
    ERA5_PATH = ERA5_PATH or discover(fs, "weatherbench2/datasets/era5", ["240x121", "with_poles", "-6h-"], prefer=["2023_01_10"])
    print("\nUsing HRES:", HRES_PATH, "\nUsing HRES (coarse, upper air):", HRES_COARSE_PATH, "\nUsing ERA5:", ERA5_PATH)
    try:
        hres = xr.open_zarr(HRES_PATH, storage_options={"token": "anon"})
        era5 = xr.open_zarr(ERA5_PATH, storage_options={"token": "anon"})
        hres_c = xr.open_zarr(HRES_COARSE_PATH, storage_options={"token": "anon"})
    except Exception as e:
        print("open_zarr failed:", repr(e)[:200])
        print('-> run  !pip install -q "zarr<3"  then Run > Restart & run all')
        raise

print("\nHRES variables:", sorted(hres.data_vars))
print("HRES init range:", str(hres.time.values[0])[:16], "->", str(hres.time.values[-1])[:16])
print("HRES leads (h):", (pd.to_timedelta(hres.prediction_timedelta.values) / pd.Timedelta("1h")).astype(int).tolist())
if "level" in hres.dims: print("HRES levels:", hres.level.values.tolist())
print("ERA5 range:", str(era5.time.values[0])[:10], "->", str(era5.time.values[-1])[:10])

# %%
# ---- 4. Check variables, pick precip source, estimate download size ----------------
H = pd.Timedelta("1h")
AVAIL_TD = pd.to_timedelta(hres.prediction_timedelta.values)

def lead_spec(kind, L):
    """list of timedeltas needed for forecast day L."""
    if kind == "rain":  return [24 * L * H]
    if kind == "day12": return [(24 * L - 12) * H]
    return [24 * L * H]

# Precipitation: prefer a 24 h field; else sum 6 h fields; else difference an accumulated field.
PRECIP_MODE = None
for cand, mode in [("total_precipitation_24hr", "24h"), ("total_precipitation_6hr", "6h"), ("total_precipitation", "accum")]:
    if cand in hres.data_vars:
        FC_VARS["rain"] = (cand, None, "rain"); PRECIP_MODE = mode; break
print("Precip source:", FC_VARS["rain"][0] if PRECIP_MODE else "NONE FOUND", "| mode:", PRECIP_MODE)

def needed_tds(name):
    var, lev, kind = FC_VARS[name]
    tds = set()
    for L in LEADS:
        if name == "rain" and PRECIP_MODE == "6h":
            tds |= {(24 * L - k) * H for k in (18, 12, 6, 0)}
        elif name == "rain" and PRECIP_MODE == "accum":
            tds |= {24 * (L - 1) * H, 24 * L * H}
        else:
            tds |= set(lead_spec(kind, L))
    return sorted(tds)

def ordered_slice(coord, lo, hi):
    v = coord.values
    return slice(lo - 1e-6, hi + 1e-6) if v[0] < v[-1] else slice(hi + 1e-6, lo - 1e-6)

def crop(da):
    da = da.sel(latitude=ordered_slice(da.latitude, LAT_MIN, LAT_MAX),
                longitude=ordered_slice(da.longitude, LON_MIN, LON_MAX))
    return da.sortby("latitude")

def source(name):
    return hres_c if (UPPER_AIR_FROM_COARSE and name in UPPER_AIR) else hres

INITS_ALL = pd.DatetimeIndex(hres.time.values)
INITS_ALL = INITS_ALL[(INITS_ALL.hour == 0) & INITS_ALL.year.isin(YEARS)]

def touched_gb(da, sel_idx):
    """Estimate bytes read from zarr: every chunk touched is read in full."""
    chunks = getattr(da.data, "chunks", None)
    if chunks is None: return np.nan
    n_chunks, chunk_elems = 1, 1
    for dim, ch in zip(da.dims, chunks):
        bounds = np.cumsum((0,) + tuple(ch))
        idx = sel_idx.get(dim, np.arange(da.sizes[dim]))
        touched = np.unique(np.searchsorted(bounds, idx, side="right") - 1)
        n_chunks *= len(touched); chunk_elems *= max(ch)
    return n_chunks * chunk_elems * da.dtype.itemsize / 1e9

def box_idx(ds, margin=0.0):
    la, lo = ds.latitude.values, ds.longitude.values
    return (np.where((la >= LAT_MIN - margin - 1e-6) & (la <= LAT_MAX + margin + 1e-6))[0],
            np.where((lo >= LON_MIN - margin - 1e-6) & (lo <= LON_MAX + margin + 1e-6))[0])

ACTIVE, total_full, total_now = {}, 0.0, 0.0
print(f"{'var':6s} {'wb2 name':26s} {'source':7s} {'this run GB':>11s} {'full run GB':>11s}  status")
for name, (var, lev, kind) in FC_VARS.items():
    ds = source(name)
    tag = "5.6°" if ds is not hres else "1.5°"
    if var not in ds.data_vars:
        print(f"{name:6s} {var:26s} {tag:7s} {'-':>11s} {'-':>11s}  missing -> skipped"); continue
    da, tds = ds[var], needed_tds(name)
    avail = pd.to_timedelta(ds.prediction_timedelta.values)
    if not set(tds) <= set(avail):
        print(f"{name:6s} {var:26s} {tag:7s} {'-':>11s} {'-':>11s}  leads not available -> skipped"); continue
    li, oi = box_idx(ds, margin=6.0 if ds is not hres else 0.0)
    t_all = pd.DatetimeIndex(ds.time.values)
    sel = {"latitude": li, "longitude": oi, "prediction_timedelta": np.where(avail.isin(tds))[0]}
    if lev is not None and "level" in da.dims:
        sel["level"] = np.where(ds.level.values == lev)[0]
    gb_now = touched_gb(da, {**sel, "time": np.where(t_all.isin(INITS_ALL))[0]})
    full = t_all[(t_all.hour == 0) & t_all.year.isin(FULL_YEARS)]
    gb_full = touched_gb(da, {**sel, "time": np.where(t_all.isin(full))[0]})
    ok = np.isnan(gb_full) or total_full + gb_full <= DOWNLOAD_BUDGET_GB
    if ok:
        ACTIVE[name] = FC_VARS[name]
        total_full += 0 if np.isnan(gb_full) else gb_full
        total_now += 0 if np.isnan(gb_now) else gb_now
    print(f"{name:6s} {var:26s} {tag:7s} {gb_now:11.1f} {gb_full:11.1f}  {'OK' if ok else 'over budget -> skipped'}")
print(f"\nThis run: ~{total_now:.1f} GB ({len(INITS_ALL)} init dates) | full 2016-2022 run: ~{total_full:.1f} GB")
print(f"Rough time at 50 MB/s: this run ~{total_now * 1e3 / 50 / 60:.0f} min, full run ~{total_full * 1e3 / 50 / 60:.0f} min "
      f"(compressed transfer is usually 2-4x smaller)")
assert "rain" in ACTIVE, "Rainfall is required. Raise DOWNLOAD_BUDGET_GB or check the variable list above."

# %%
# ---- 5. Target grid, IMD rainfall -> 1.5°, land mask, regions ---------------------
TLAT = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-6, RES), 3)
TLON = np.round(np.arange(LON_MIN, LON_MAX + 1e-6, RES), 3)

def load_imd_rain(years):
    if MOCK:
        return make_mock_imd(years)
    import imdlib as imd
    d = f"{OUT}/imd_raw"; os.makedirs(d, exist_ok=True)
    y0, y1 = years[0], years[-1] + 1          # +1 year so Day-10 forecasts in late Dec have truth
    for y in range(y0, y1 + 1):               # one year at a time, skip what is already there
        f = f"{d}/rain/{y}.grd"
        if os.path.exists(f) and os.path.getsize(f) > 1e6:
            print(f"IMD {y}: already downloaded", flush=True); continue
        t0 = time.time()
        print(f"IMD {y}: downloading...", flush=True)
        for attempt in range(1, 6):                   # the IMD server often times out: retry with a pause
            try:
                imd.get_data("rain", y, y, fn_format="yearwise", file_dir=d); break
            except Exception as e:
                if attempt == 5: raise
                print(f"   attempt {attempt} failed ({type(e).__name__}); retrying in {20 * attempt}s", flush=True)
                time.sleep(20 * attempt)
        print(f"IMD {y}: done in {time.time() - t0:.0f}s", flush=True)
    ds = imd.open_data("rain", y0, y1, "yearwise", d).get_xarray()
    da = ds["rain"] if "rain" in ds else ds[list(ds.data_vars)[0]]
    return da.where(da > -998)

def block_average(da, lat_name="lat", lon_name="lon"):
    """Conservative-ish regrid: average all fine points falling in each 1.5° cell (vectorised)."""
    la, lo = da[lat_name].values, da[lon_name].values
    ia = np.floor((la - TLAT[0] + RES / 2) / RES).astype(int)
    io = np.floor((lo - TLON[0] + RES / 2) / RES).astype(int)
    A = np.zeros((len(TLAT), len(la))); B = np.zeros((len(TLON), len(lo)))
    ok_a, ok_o = (ia >= 0) & (ia < len(TLAT)), (io >= 0) & (io < len(TLON))
    A[ia[ok_a], np.where(ok_a)[0]] = 1; B[io[ok_o], np.where(ok_o)[0]] = 1
    X = da.transpose("time", lat_name, lon_name).values
    valid = np.isfinite(X)
    s = np.einsum("ia,tab,jb->tij", A, np.where(valid, X, 0.0), B, optimize=True)
    n = np.einsum("ia,tab,jb->tij", A, valid.astype(float), B, optimize=True)
    total = A.sum(1)[:, None] * B.sum(1)[None, :]
    frac = np.divide(n[0], total, out=np.zeros_like(total), where=total > 0)
    mean = np.divide(s, n, out=np.full_like(s, np.nan), where=n > 0)
    out = xr.DataArray(mean.astype("float32"), dims=("date", "lat", "lon"),
                       coords={"date": pd.DatetimeIndex(da.time.values).normalize(), "lat": TLAT, "lon": TLON})
    return out, frac

IMD_OK = True
try:
    imd_fine = load_imd_rain(YEARS)
    imd_fine = imd_fine.sel(time=slice(f"{YEARS[0]}-01-01", f"{YEARS[-1] + 1}-01-15"))
    obs_rain, land_frac = block_average(imd_fine)
    print("IMD rainfall regridded:", obs_rain.shape, "| days:", obs_rain.date.size)
except Exception as e:
    IMD_OK = False
    print("!! IMD download failed:", repr(e)[:200], "\n   -> falling back to ERA5 rainfall as truth.")
    print("   Better: wait a few minutes and run this cell again (downloaded years are kept).")

# land mask: IMD coverage if available, else ERA5 land-sea mask / box
if IMD_OK:
    LAND = land_frac >= 0.5
elif "land_sea_mask" in era5:
    lsm = crop(era5["land_sea_mask"].isel(time=0) if "time" in era5["land_sea_mask"].dims else era5["land_sea_mask"])
    LAND = lsm.transpose("latitude", "longitude").values >= 0.5
else:
    LAND = np.ones((len(TLAT), len(TLON)), bool)

def region_map():
    rid = np.full((len(TLAT), len(TLON)), -1, int)
    for k, (name, boxes) in enumerate(REGIONS.items()):
        for (a0, a1, o0, o1) in boxes:
            m = (TLAT[:, None] >= a0) & (TLAT[:, None] <= a1) & (TLON[None, :] >= o0) & (TLON[None, :] <= o1)
            rid[m & (rid == -1) & LAND] = k
    return rid

RID = region_map()
for k, n in enumerate(REGION_NAMES):
    print(f"  {n:14s} {int((RID == k).sum()):3d} land cells")
xr.Dataset({"land": (("lat", "lon"), LAND.astype("int8")), "region_id": (("lat", "lon"), RID)},
           coords={"lat": TLAT, "lon": TLON}, attrs={"regions": json.dumps(REGION_NAMES)}).to_netcdf(f"{OUT}/grid_meta.nc.tmp")
os.replace(f"{OUT}/grid_meta.nc.tmp", f"{OUT}/grid_meta.nc")          # safe even if an old copy is open elsewhere

# %%
# ---- 6. Download forecasts year by year (resumable) --------------------------------
try:
    import dask
    dask.config.set(scheduler="threads", num_workers=32)
except Exception:
    pass

def fetch_var(name, inits):
    var, lev, kind = ACTIVE[name]
    ds = source(name)
    da = ds[var]
    if lev is not None and "level" in da.dims:
        da = da.sel(level=lev, drop=True)
    da = da.sel(time=inits)
    tds = needed_tds(name)
    if ds is hres:
        da = crop(da).sel(prediction_timedelta=tds).load()
        assert (da.sizes["latitude"], da.sizes["longitude"]) == (len(TLAT), len(TLON)), da.sizes
        da = da.assign_coords(latitude=TLAT, longitude=TLON)   # snap float coords (e.g. 6.0000001) to the exact grid
    else:                                   # coarse 5.6° field: crop with a margin, then interpolate to 1.5°
        da = da.sel(latitude=ordered_slice(da.latitude, LAT_MIN - 6, LAT_MAX + 6),
                    longitude=ordered_slice(da.longitude, LON_MIN - 6, LON_MAX + 6))
        da = da.sel(prediction_timedelta=tds).load().sortby("latitude")
        da = da.interp(latitude=TLAT, longitude=TLON, kwargs={"fill_value": None})
    per_lead = []
    for L in LEADS:
        if name == "rain" and PRECIP_MODE == "6h":
            x = da.sel(prediction_timedelta=[(24 * L - k) * H for k in (18, 12, 6, 0)]).sum("prediction_timedelta")
        elif name == "rain" and PRECIP_MODE == "accum":
            x = da.sel(prediction_timedelta=24 * L * H) - da.sel(prediction_timedelta=24 * (L - 1) * H)
        else:
            x = da.sel(prediction_timedelta=lead_spec(kind, L)[0])
        per_lead.append(x.drop_vars("prediction_timedelta", errors="ignore"))
    out = xr.concat(per_lead, dim=pd.Index(LEADS, name="lead"))
    # units
    if name == "rain":
        out = out * 1000.0 if float(out.max()) < 5 else out            # m -> mm
        out = out.clip(min=0)
    if name == "z500":
        out = out / 9.80665                                             # m2/s2 -> gpm
    if name == "q700":
        out = out * 1000.0                                              # kg/kg -> g/kg
    if name == "mslp":
        out = out / 100.0                                               # Pa -> hPa
    out = out.rename({"time": "init", "latitude": "lat", "longitude": "lon"}).astype("float32")
    return out.reset_coords(drop=True)

for yr in YEARS:
    path = f"{OUT}/maps/fc_{yr}.nc"
    if os.path.exists(path):
        with xr.open_dataset(path) as old:
            same = set(old.data_vars) == set(ACTIVE)
        if same:
            print(yr, "already done"); continue
        print(yr, "exists with different variables -> re-downloading"); os.remove(path)
    inits = INITS_ALL[INITS_ALL.year == yr]
    if len(inits) == 0:
        print(yr, "no inits"); continue
    t0 = time.time()
    ds_y = xr.Dataset({n: fetch_var(n, inits) for n in ACTIVE})
    ds_y = ds_y.assign_coords(lat=TLAT, lon=TLON).transpose("init", "lead", "lat", "lon")
    ds_y.to_netcdf(path + ".tmp"); os.replace(path + ".tmp", path)
    print(f"{yr}: {len(inits)} inits, vars={list(ACTIVE)}  ({time.time() - t0:.0f}s)")

# %%
# ---- 7. Observations on the same grid: IMD rain (or ERA5), ERA5 t2m at 12 UTC -----
fc_all = xr.open_mfdataset(sorted(glob.glob(f"{OUT}/maps/fc_*.nc")), combine="nested", concat_dim="init") \
    if not MOCK else xr.concat([xr.open_dataset(p).load() for p in sorted(glob.glob(f"{OUT}/maps/fc_*.nc"))], "init")
DATES = pd.date_range(f"{YEARS[0]}-01-01", f"{YEARS[-1] + 1}-01-12", freq="D")
DATES = DATES[DATES <= pd.Timestamp(era5.time.values[-1]).normalize()]

def era5_daily(var, hour, dates):
    t = dates + pd.Timedelta(hours=hour)
    t = t[pd.DatetimeIndex(t).isin(pd.DatetimeIndex(era5.time.values))]
    da = crop(era5[var].sel(time=t)).load()
    assert (da.sizes["latitude"], da.sizes["longitude"]) == (len(TLAT), len(TLON)), da.sizes
    da = da.rename({"time": "date", "latitude": "lat", "longitude": "lon"}).assign_coords(lat=TLAT, lon=TLON)
    return da.assign_coords(date=pd.DatetimeIndex(da.date.values).normalize())

obs = {}
if "t2m" in ACTIVE and "2m_temperature" in era5:
    obs["t2m"] = era5_daily("2m_temperature", 12, DATES).astype("float32")
if not IMD_OK:
    pv = "total_precipitation_24hr" if "total_precipitation_24hr" in era5 else None
    assert pv, "No IMD and no ERA5 precipitation: cannot build rainfall truth."
    r = era5_daily(pv, 24, DATES)      # 24 h accumulation ending 00 UTC next day
    r = r.assign_coords(date=r.date - pd.Timedelta(days=1)) * 1000.0
    obs_rain = r.clip(min=0).astype("float32")

# --- IMD day alignment check: IMD "date" convention vs UTC forecast days.
# Pick the shift (-1, 0, +1 day) that best matches Day-1 forecasts over all-India land.
def best_shift(fc_rain_l1, obs_r):
    scores = {}
    fcm = fc_rain_l1.where(LAND).mean(("lat", "lon")).to_series()
    fcm.index = pd.DatetimeIndex(fcm.index).normalize()     # valid date of Day 1 = init date
    for s in (-1, 0, 1):
        o = obs_r.assign_coords(date=obs_r.date - pd.Timedelta(days=s)).where(LAND).mean(("lat", "lon")).to_series()
        j = pd.concat([fcm, o], axis=1, join="inner").dropna()
        scores[s] = j.corr().iloc[0, 1] if len(j) > 30 else np.nan
    return scores

sc = best_shift(fc_all["rain"].sel(lead=1).load(), obs_rain)
SHIFT = max(sc, key=lambda k: -1 if np.isnan(sc[k]) else sc[k])
print("Day-1 correlation by IMD shift:", {k: round(v, 3) for k, v in sc.items()}, "-> using shift", SHIFT)
obs_rain = obs_rain.assign_coords(date=obs_rain.date - pd.Timedelta(days=SHIFT))
obs["rain"] = obs_rain

for yr in YEARS:
    o = xr.Dataset({k: v.sel(date=str(yr)) for k, v in obs.items()})
    o.to_netcdf(f"{OUT}/maps/obs_{yr}.nc")
print("Observation maps saved:", list(obs))

# %%
# ---- 8. Region table: forecast vs observed, errors, run-to-run jumps --------------
rows = []
for yr in YEARS:
    p = f"{OUT}/maps/fc_{yr}.nc"
    if not os.path.exists(p): continue
    fc = xr.open_dataset(p).load()
    inits = pd.DatetimeIndex(fc.init.values)
    valid = inits.values[:, None] + (np.array(LEADS) - 1)[None, :] * np.timedelta64(1, "D")
    vda = xr.DataArray(valid, dims=("init", "lead"), coords={"init": fc.init, "lead": fc.lead})
    obs_on = {}                                                    # observations re-indexed to init × lead
    for k, o in obs.items():
        if k not in fc: continue
        okv = vda.isin(o.date.values)
        obs_on[k] = o.sel(date=vda.where(okv, o.date.values[0])).where(okv).drop_vars("date")
    base = pd.DataFrame({"init": np.repeat(inits.values, len(LEADS)),
                         "lead": np.tile(LEADS, len(inits)), "valid_date": valid.ravel()})
    flat = lambda a: a.transpose("init", "lead").values.ravel()
    for r, rname in enumerate(REGION_NAMES):
        m = xr.DataArray(RID == r, dims=("lat", "lon"), coords={"lat": fc.lat, "lon": fc.lon})
        d = base.copy(); d["region"] = rname
        for v in fc.data_vars:                                     # region-mean forecast of every variable
            d[f"fc_{v}"] = flat(fc[v].where(m).mean(("lat", "lon")))
        d["fc_rain_max"] = flat(fc["rain"].where(m).max(("lat", "lon")))   # how "peaky" the rain forecast is
        for k, o in obs_on.items():
            d[f"obs_{k}"] = flat(o.where(m).mean(("lat", "lon")))
            d[f"{k}_rmse"] = flat(np.sqrt(((fc[k] - o) ** 2).where(m).mean(("lat", "lon"))))
        rows.append(d)
    print(yr, "done")

df = pd.concat(rows, ignore_index=True)
df["init"] = pd.to_datetime(df["init"]); df["valid_date"] = pd.to_datetime(df["valid_date"])
for k in obs:
    if f"fc_{k}" in df:
        df[f"{k}_err"] = df[f"fc_{k}"] - df[f"obs_{k}"]
if "t2m_err" in df: df["t2m_abs"] = df["t2m_err"].abs()

# run-to-run jump: today's Day-L forecast minus yesterday's Day-(L+1) forecast for the SAME valid date
fcols = [c for c in df.columns if c.startswith("fc_")]
prev = df[["init", "lead", "region"] + fcols].copy()
prev["init"] = prev["init"] + pd.Timedelta(days=1); prev["lead"] = prev["lead"] - 1
prev = prev.rename(columns={c: c + "_prev" for c in fcols})
df = df.merge(prev, on=["init", "lead", "region"], how="left")
for c in fcols:
    df[c.replace("fc_", "jump_")] = df[c] - df[c + "_prev"]
df = df.drop(columns=[c + "_prev" for c in fcols])

SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJAS", 7: "JJAS", 8: "JJAS", 9: "JJAS", 10: "ON", 11: "ON"}
df["month"] = df["valid_date"].dt.month
df["season"] = df["month"].map(SEASON)
df["split"] = np.where(df["init"].dt.year.isin(TRAIN_YEARS), "train", "test")
df = df.dropna(subset=["obs_rain"]).reset_index(drop=True)
print(df.shape); df.head()

# %%
# ---- 9. Bust labels -------------------------------------------------------------------
targets = [("rain_rmse", "bust_rain")] + ([("t2m_abs", "bust_t2m")] if "t2m_abs" in df else [])
thr_rows = []
for col, lab in targets:
    q = (df[df.split == "train"].groupby(["region", "lead", "season"])[col]
         .quantile(BUST_Q).rename(f"thr_{col}").reset_index())
    q[f"thr_{col}"] = q[f"thr_{col}"].clip(lower=FLOOR[col])
    df = df.merge(q, on=["region", "lead", "season"], how="left")
    df[lab] = (df[col] > df[f"thr_{col}"]).astype(int)
    df[f"sev_{col}"] = df[col] / df[f"thr_{col}"]           # >1 = bust, bigger = worse
    thr_rows.append(q.set_index(["region", "lead", "season"]))
df["bust"] = df[[lab for _, lab in targets]].max(axis=1)
pd.concat(thr_rows, axis=1).reset_index().to_csv(f"{OUT}/thresholds.csv", index=False)

print("Bust rate (train / test):")
print(df.groupby("split")[[lab for _, lab in targets] + ["bust"]].mean().round(3))
save_table(df, f"{OUT}/regions.parquet")

# %%
# ---- 10. First charts -----------------------------------------------------------------
import matplotlib.pyplot as plt
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
COLS = ["#1F3864", "#0070C0", "#E8772E", "#2E9E5B", "#F2A516", "#D64541", "#7B4FA0"]

fig, axes = plt.subplots(1, 2 if "t2m_abs" in df else 1, figsize=(12, 4.2), squeeze=False)
for i, rname in enumerate(REGION_NAMES):
    g = df[df.region == rname].groupby("lead")
    axes[0, 0].plot(LEADS, g["rain_rmse"].median().reindex(LEADS), "-o", ms=3, color=COLS[i], label=rname)
    if "t2m_abs" in df:
        axes[0, 1].plot(LEADS, g["t2m_abs"].median().reindex(LEADS), "-o", ms=3, color=COLS[i])
axes[0, 0].set(title="Rainfall error grows with lead day", xlabel="Lead day", ylabel="Median grid RMSE (mm/day)")
if "t2m_abs" in df:
    axes[0, 1].set(title="2 m temperature error", xlabel="Lead day", ylabel="Median |error| (K)")
axes[0, 0].legend(fontsize=8, frameon=False, ncol=2)
plt.tight_layout(); plt.savefig(f"{OUT}/fig_error_vs_lead.png"); plt.show()

# absolute large-error rate: how often each region/month has rain RMSE above the monsoon-wide 90th pct
big = df["rain_rmse"] > df.loc[df.split == "train", "rain_rmse"].quantile(0.9)
hm = df.assign(big=big).groupby(["region", "month"])["big"].mean().unstack().reindex(REGION_NAMES)
fig, ax = plt.subplots(figsize=(10, 3.6))
im = ax.imshow(hm.values, cmap="YlOrRd", aspect="auto")
ax.set_yticks(range(len(hm.index)), hm.index); ax.set_xticks(range(hm.shape[1]), [pd.Timestamp(2000, m, 1).strftime("%b") for m in hm.columns])
ax.set_title("Where and when big rainfall errors happen (share of forecasts)")
plt.colorbar(im, ax=ax, fraction=0.03); plt.tight_layout(); plt.savefig(f"{OUT}/fig_bust_calendar.png"); plt.show()

# %%
# ---- 11. Event sanity check: were the famous events busts? ----------------------------
ev_rows = []
for name, region, d0, d1, var in EVENTS:
    sub = df[(df.region == region) & (df.valid_date >= d0) & (df.valid_date <= d1)]
    if sub.empty:
        continue
    lab = "bust_rain" if var == "rain" else "bust_t2m"
    if lab not in sub: continue
    by = sub.groupby("lead")[lab].max().reindex(LEADS)
    ev_rows.append({"event": name, "region": region, **{f"D{L}": ("X" if by[L] == 1 else ".") for L in LEADS},
                    "obs": round(sub[f"obs_{var}"].max(), 1), "split": sub.split.iloc[0]})
ev = pd.DataFrame(ev_rows)
print("X = forecast bust for that lead day during the event window")
print(ev.to_string(index=False) if len(ev) else "No events inside the data range.")
ev.to_csv(f"{OUT}/event_check.csv", index=False)

# %%
# ---- 12. Zip everything for download --------------------------------------------------
if os.path.exists(f"{OUT}/imd_raw"):
    shutil.rmtree(f"{OUT}/imd_raw")            # raw IMD files are not needed any more
zip_path = shutil.make_archive(OUT, "zip", OUT)
print("Download this file from the Output panel:", zip_path, f"({os.path.getsize(zip_path) / 1e6:.0f} MB)")
