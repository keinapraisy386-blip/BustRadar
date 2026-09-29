# %% [markdown]
# # BustRadar — Day 1b: Extra data for weather-system physics
#
# Run this **after notebook 01**, in the same Kaggle notebook (new cell below) or a new one with the
# notebook-01 output attached. Internet **ON**. It only **adds** files; nothing from notebook 01 is re-downloaded.
#
# **Adds**
# | forecast (ECMWF HRES) | truth | used for |
# |---|---|---|
# | daily max 10 m wind (1.5°) | ERA5 daily max 10 m wind | **wind busts** (cyclones, strong winds) |
# | daytime max 2 m temperature (1.5°) | **IMD Tmax** (ERA5 fallback) | **heat-wave busts** |
# | u/v 200 hPa, T 500/700/850, w 500, q 850 (5.6° → 1.5°) | ERA5 500 hPa height | **pattern busts**, jet, shear, vorticity, instability, moisture flux |
# | — | MJO (RMM), ENSO (Niño-3.4), IOD | large-scale climate drivers |
#
# Output goes into the same `bustradar_data/` folder: `maps/fcx_YYYY.nc`, `maps/obsx_YYYY.nc`, `climate_*.csv`.

# %%
# ---- 1. Setup ----------------------------------------------------------------------------
import os, sys, subprocess, glob, json, time, warnings, io
ON_KAGGLE = os.path.exists("/kaggle")
if ON_KAGGLE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gcsfs", "zarr", "imdlib"], check=False)
import numpy as np, pandas as pd, xarray as xr
warnings.filterwarnings("ignore")

MOCK = globals().get("MOCK", False)
OUT = globals().get("OUT") or ("/kaggle/working/bustradar_data" if ON_KAGGLE else "./bustradar_data")
if not os.path.exists(f"{OUT}/grid_meta.nc"):
    hits = glob.glob("/kaggle/input/**/grid_meta.nc", recursive=True) + glob.glob("./**/bustradar_data/grid_meta.nc", recursive=True)
    if not hits:
        raise FileNotFoundError("Run notebook 01 first (grid_meta.nc not found).")
    src = os.path.dirname(hits[0])
    if src != OUT:                       # read-only input: copy the small files so we can add to them
        import shutil; shutil.copytree(src, OUT, dirs_exist_ok=True)
os.makedirs(f"{OUT}/maps", exist_ok=True)

YEARS = globals().get("YEARS_X") or sorted(int(os.path.basename(p)[3:7]) for p in glob.glob(f"{OUT}/maps/fc_*.nc"))
LEADS = list(range(1, 11))
DOWNLOAD_BUDGET_GB = 80
with xr.open_dataset(f"{OUT}/grid_meta.nc") as _g:
    grid = _g.load()
TLAT, TLON = grid.lat.values, grid.lon.values
LAND = grid.land.values.astype(bool)
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, RES = TLAT[0], TLAT[-1], TLON[0], TLON[-1], 1.5
H = pd.Timedelta("1h")
print("Years:", YEARS, "| grid", len(TLAT), "x", len(TLON), "| out:", OUT)

# %%
# ---- 2. Open WeatherBench 2 --------------------------------------------------------------
def discover(fs, prefix, must, prefer=()):
    items = [p for p in fs.ls(prefix) if p.endswith(".zarr")]
    cands = [p for p in items if all(m in p for m in must)]
    for pref in prefer:
        c2 = [p for p in cands if pref in p]
        if c2: cands = c2
    if not cands: raise RuntimeError(f"No store in {prefix} matches {must}")
    return "gs://" + sorted(cands)[0]

if MOCK:
    hres, era5 = make_mock_wb2()
    hres_c = hres.isel(latitude=slice(None, None, 3), longitude=slice(None, None, 3))
    era5_c = era5_coarse_mock()
else:
    import gcsfs
    fs = gcsfs.GCSFileSystem(token="anon")
    so = {"token": "anon"}
    P = {"hres": discover(fs, "weatherbench2/datasets/hres", ["240x121", "with_poles"], ["0012"]),
         "hres_c": discover(fs, "weatherbench2/datasets/hres", ["64x32"], ["0012"]),
         "era5": discover(fs, "weatherbench2/datasets/era5", ["240x121", "with_poles", "-6h-"], ["2023_01_10"]),
         "era5_c": discover(fs, "weatherbench2/datasets/era5", ["64x32", "-6h-"], ["2023_01_10"])}
    for k, v in P.items(): print(f"{k:7s} {v}")
    hres, hres_c = xr.open_zarr(P["hres"], storage_options=so), xr.open_zarr(P["hres_c"], storage_options=so)
    era5, era5_c = xr.open_zarr(P["era5"], storage_options=so), xr.open_zarr(P["era5_c"], storage_options=so)
print("ERA5 vars:", sorted(era5.data_vars)[:30])

# %%
# ---- 3. What to download -----------------------------------------------------------------
# One WB2 variable at several levels costs the same as one level (all levels share a chunk),
# so each variable is fetched once with all the levels we need.
FCX = [  # (wb2 variable, levels, source, timing) -> output names
    ("10m_wind_speed",      None,            "fine",   "max4"),   # -> wind10max
    ("2m_temperature",      None,            "fine",   "max2"),   # -> tmax  (max of 06 & 12 UTC)
    ("u_component_of_wind", [200],           "coarse", "day00"),  # -> u200
    ("v_component_of_wind", [200],           "coarse", "day00"),  # -> v200
    ("temperature",         [500, 700, 850], "coarse", "day00"),  # -> t500, t700, t850
    ("vertical_velocity",   [500],           "coarse", "day00"),  # -> w500
    ("specific_humidity",   [850],           "coarse", "day00"),  # -> q850
]
SHORT = {"u_component_of_wind": "u", "v_component_of_wind": "v", "temperature": "t",
         "vertical_velocity": "w", "specific_humidity": "q"}

def tds_for(timing, L):
    if timing == "max4": return [(24 * L - k) * H for k in (18, 12, 6, 0)]   # 06, 12, 18, 24 UTC of day L
    if timing == "max2": return [(24 * L - k) * H for k in (18, 12)]         # 06 and 12 UTC (daytime)
    return [24 * L * H]

def all_tds(timing):
    return sorted({t for L in LEADS for t in tds_for(timing, L)})

def ordered_slice(coord, lo, hi):
    v = coord.values
    return slice(lo - 1e-6, hi + 1e-6) if v[0] < v[-1] else slice(hi + 1e-6, lo - 1e-6)

def to_grid(da, coarse):
    """Crop to India; fine data is snapped to the exact grid, coarse data is interpolated to it."""
    m = 6.0 if coarse else 0.0
    da = da.sel(latitude=ordered_slice(da.latitude, LAT_MIN - m, LAT_MAX + m),
                longitude=ordered_slice(da.longitude, LON_MIN - m, LON_MAX + m)).load().sortby("latitude")
    if coarse:
        return da.interp(latitude=TLAT, longitude=TLON, kwargs={"fill_value": None})
    assert (da.sizes["latitude"], da.sizes["longitude"]) == (len(TLAT), len(TLON)), da.sizes
    return da.assign_coords(latitude=TLAT, longitude=TLON)

def touched_gb(da, sel_idx):
    chunks = getattr(da.data, "chunks", None)
    if chunks is None: return np.nan
    n, e = 1, 1
    for dim, ch in zip(da.dims, chunks):
        b = np.cumsum((0,) + tuple(ch)); idx = sel_idx.get(dim, np.arange(da.sizes[dim]))
        n *= len(np.unique(np.searchsorted(b, idx, side="right") - 1)); e *= max(ch)
    return n * e * da.dtype.itemsize / 1e9

total = 0.0
print(f"{'variable':22s} {'levels':14s} {'src':6s} {'est GB':>7s}")
for var, levs, src, timing in FCX:
    ds = hres if src == "fine" else hres_c
    if var not in ds: print(f"{var:22s} missing -> skipped"); continue
    t_all = pd.DatetimeIndex(ds.time.values)
    inits = t_all[(t_all.hour == 0) & t_all.year.isin(YEARS)]
    avail = pd.to_timedelta(ds.prediction_timedelta.values)
    la, lo = ds.latitude.values, ds.longitude.values
    m = 6 if src == "coarse" else 0
    sel = {"time": np.where(t_all.isin(inits))[0],
           "prediction_timedelta": np.where(avail.isin(all_tds(timing)))[0],
           "latitude": np.where((la >= LAT_MIN - m - 1e-6) & (la <= LAT_MAX + m + 1e-6))[0],
           "longitude": np.where((lo >= LON_MIN - m - 1e-6) & (lo <= LON_MAX + m + 1e-6))[0]}
    if levs and "level" in ds[var].dims: sel["level"] = np.where(np.isin(ds.level.values, levs))[0]
    gb = touched_gb(ds[var], sel); total += 0 if np.isnan(gb) else gb
    print(f"{var:22s} {str(levs):14s} {src:6s} {gb:7.1f}")
print(f"Total ~{total:.0f} GB (~{total * 1e3 / 50 / 60:.0f} min at 50 MB/s; usually faster, data is compressed)")

# %%
# ---- 4. Download extra forecast fields, year by year (resumable) ---------------------------
try:
    import dask; dask.config.set(scheduler="threads", num_workers=32)
except Exception:
    pass

def fetch(var, levs, src, timing, inits):
    ds = hres if src == "fine" else hres_c
    if var not in ds: return {}
    avail = set(pd.to_timedelta(ds.prediction_timedelta.values))
    use = [t for t in all_tds(timing) if t in avail]              # real WB2 is 6-hourly, so all are there
    da = ds[var].sel(time=inits, prediction_timedelta=use)
    if levs and "level" in da.dims: da = da.sel(level=levs)
    da = to_grid(da, src == "coarse")
    out = {}
    lev_list = levs if (levs and "level" in da.dims) else [None]
    for lev in lev_list:
        x = da.sel(level=lev, drop=True) if lev is not None else da
        per = []
        for L in LEADS:
            y = x.sel(prediction_timedelta=[t for t in tds_for(timing, L) if t in avail])
            y = y.max("prediction_timedelta") if timing in ("max4", "max2") else y.isel(prediction_timedelta=0, drop=True)
            per.append(y.drop_vars("prediction_timedelta", errors="ignore"))
        y = xr.concat(per, dim=pd.Index(LEADS, name="lead"))
        name = {"10m_wind_speed": "wind10max", "2m_temperature": "tmax"}.get(var) or f"{SHORT[var]}{lev}"
        if name.startswith("q"): y = y * 1000.0                      # kg/kg -> g/kg
        out[name] = y.rename({"time": "init", "latitude": "lat", "longitude": "lon"}) \
                     .transpose("init", "lead", "lat", "lon").astype("float32").reset_coords(drop=True)
    return out

for yr in YEARS:
    path = f"{OUT}/maps/fcx_{yr}.nc"
    if os.path.exists(path): print(yr, "already done"); continue
    t_all = pd.DatetimeIndex(hres.time.values)
    inits = t_all[(t_all.hour == 0) & (t_all.year == yr)]
    t0 = time.time(); fields = {}
    for spec in FCX:
        fields.update(fetch(*spec, inits))
    ds_y = xr.Dataset(fields).assign_coords(lat=TLAT, lon=TLON)
    ds_y.to_netcdf(path + ".tmp"); os.replace(path + ".tmp", path)
    print(f"{yr}: {list(fields)}  ({time.time() - t0:.0f}s)", flush=True)

# %%
# ---- 5. Extra truth: ERA5 daily max wind + 500 hPa height, IMD Tmax -----------------------
DATES = pd.date_range(f"{YEARS[0]}-01-01", f"{YEARS[-1] + 1}-01-12", freq="D")

def era5_times(ds, dates, hours):
    tt = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in dates for h in hours])
    return tt[tt.isin(pd.DatetimeIndex(ds.time.values))]

def era5_daily(ds, var, dates, hours, how, coarse=False, level=None):
    tt = era5_times(ds, dates, hours)
    da = ds[var].sel(time=tt)
    if level is not None: da = da.sel(level=level, drop=True)
    da = to_grid(da, coarse)
    day = pd.DatetimeIndex(da.time.values) - pd.Timedelta(hours=min(hours))   # label by the day the window starts
    da = da.assign_coords(time=day.normalize())
    da = getattr(da.groupby("time"), how)() if how != "first" else da.groupby("time").first()
    return da.rename({"time": "date", "latitude": "lat", "longitude": "lon"}).astype("float32")

obsx = {}
if "10m_wind_speed" in era5:
    obsx["wind10max"] = era5_daily(era5, "10m_wind_speed", DATES, (6, 12, 18, 24), "max")
elif {"10m_u_component_of_wind", "10m_v_component_of_wind"} <= set(era5.data_vars):
    # speed must be computed per time step, then the daily max taken
    tt = era5_times(era5, DATES, (6, 12, 18, 24))
    uu = to_grid(era5["10m_u_component_of_wind"].sel(time=tt), False)
    vv = to_grid(era5["10m_v_component_of_wind"].sel(time=tt), False)
    sp = np.sqrt(uu ** 2 + vv ** 2)
    sp = sp.assign_coords(time=(pd.DatetimeIndex(sp.time.values) - pd.Timedelta(hours=6)).normalize())
    obsx["wind10max"] = sp.groupby("time").max().rename({"time": "date", "latitude": "lat", "longitude": "lon"}).astype("float32")
obsx["tmax_era5"] = era5_daily(era5, "2m_temperature", DATES, (6, 12), "max")
if "geopotential" in era5_c:
    obsx["z500"] = era5_daily(era5_c, "geopotential", DATES, (24,), "first", coarse=True, level=500) / 9.80665
    # labelled by the valid day: 00 UTC at the END of day d, matching the forecast's z500 at lead 24L
print("ERA5 truth:", list(obsx))

# IMD Tmax (1°) -> 1.5°; used as heat truth when available
def block_average(da, lat_name="lat", lon_name="lon"):
    la, lo = da[lat_name].values, da[lon_name].values
    ia = np.floor((la - TLAT[0] + RES / 2) / RES).astype(int); io = np.floor((lo - TLON[0] + RES / 2) / RES).astype(int)
    A = np.zeros((len(TLAT), len(la))); B = np.zeros((len(TLON), len(lo)))
    ok_a, ok_o = (ia >= 0) & (ia < len(TLAT)), (io >= 0) & (io < len(TLON))
    A[ia[ok_a], np.where(ok_a)[0]] = 1; B[io[ok_o], np.where(ok_o)[0]] = 1
    X = da.transpose("time", lat_name, lon_name).values; v = np.isfinite(X)
    s = np.einsum("ia,tab,jb->tij", A, np.where(v, X, 0.0), B, optimize=True)
    n = np.einsum("ia,tab,jb->tij", A, v.astype(float), B, optimize=True)
    mean = np.divide(s, n, out=np.full_like(s, np.nan), where=n > 0)
    return xr.DataArray(mean.astype("float32"), dims=("date", "lat", "lon"),
                        coords={"date": pd.DatetimeIndex(da.time.values).normalize(), "lat": TLAT, "lon": TLON})

def load_imd_tmax(years):
    if MOCK: return make_mock_imd_tmax(years)
    import imdlib as imd
    d = f"{OUT}/imd_raw"; os.makedirs(d, exist_ok=True)
    y0, y1 = years[0], years[-1] + 1
    for y in range(y0, y1 + 1):
        f = f"{d}/tmax/{y}.GRD"
        if glob.glob(f"{d}/tmax/{y}.*") and os.path.getsize(glob.glob(f"{d}/tmax/{y}.*")[0]) > 1e5:
            print(f"IMD Tmax {y}: already downloaded", flush=True); continue
        t0 = time.time(); print(f"IMD Tmax {y}: downloading...", flush=True)
        for attempt in range(1, 6):
            try:
                imd.get_data("tmax", y, y, fn_format="yearwise", file_dir=d); break
            except Exception as e:
                if attempt == 5: raise
                print(f"   attempt {attempt} failed ({type(e).__name__}); retrying in {20 * attempt}s", flush=True)
                time.sleep(20 * attempt)
        print(f"IMD Tmax {y}: done in {time.time() - t0:.0f}s", flush=True)
    ds = imd.open_data("tmax", y0, y1, "yearwise", d).get_xarray()
    da = ds["tmax"] if "tmax" in ds else ds[list(ds.data_vars)[0]]
    return da.where((da > -90) & (da < 60))

try:
    imd_tmax = block_average(load_imd_tmax(YEARS)) + 273.15
    # alignment check against ERA5 daytime max (should be best at shift 0)
    e = obsx["tmax_era5"].where(LAND).mean(("lat", "lon")).to_series()
    sc = {}
    for s in (-1, 0, 1):
        o = imd_tmax.assign_coords(date=imd_tmax.date - pd.Timedelta(days=s)).where(LAND).mean(("lat", "lon")).to_series()
        j = pd.concat([e, o], axis=1, join="inner").dropna(); sc[s] = j.corr().iloc[0, 1] if len(j) > 30 else np.nan
    s_best = max(sc, key=lambda k: -1 if np.isnan(sc[k]) else sc[k])
    print("IMD Tmax vs ERA5 correlation by shift:", {k: round(v, 3) for k, v in sc.items()}, "-> shift", s_best)
    obsx["tmax"] = imd_tmax.assign_coords(date=imd_tmax.date - pd.Timedelta(days=s_best))
    TMAX_SRC = "IMD"
except Exception as ex:
    print("!! IMD Tmax failed:", repr(ex)[:200], "-> using ERA5 daytime max as heat truth")
    obsx["tmax"] = obsx["tmax_era5"]; TMAX_SRC = "ERA5"

for yr in YEARS:
    o = xr.Dataset({k: v.sel(date=slice(f"{yr}-01-01", f"{yr + 1}-01-12")) for k, v in obsx.items()})
    o.attrs["tmax_source"] = TMAX_SRC
    o.to_netcdf(f"{OUT}/maps/obsx_{yr}.nc")
print("Saved obsx files | heat truth:", TMAX_SRC)

# %%
# ---- 6. Climate drivers: MJO (RMM), ENSO (Niño-3.4), IOD (DMI) -----------------------------
def get_text(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BustRadar research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")

def parse_psl_monthly(txt, name):
    rows = []
    for line in txt.splitlines():
        p = line.split()
        if len(p) == 13 and p[0].isdigit() and len(p[0]) == 4:
            for m, v in enumerate(p[1:], 1):
                v = float(v)
                if v > -90: rows.append((int(p[0]), m, v))
    return pd.DataFrame(rows, columns=["year", "month", name])

if not MOCK:
    try:
        txt = get_text("http://www.bom.gov.au/climate/mjo/graphics/rmm.74toRealtime.txt")
        rows = []
        for line in txt.splitlines():
            p = line.replace(",", " ").split()
            if len(p) >= 7 and p[0].isdigit() and len(p[0]) == 4:
                y, m, d, r1, r2, ph, amp = p[:7]
                if abs(float(r1)) < 900: rows.append((f"{y}-{int(m):02d}-{int(d):02d}", float(r1), float(r2), int(float(ph)), float(amp)))
        rmm = pd.DataFrame(rows, columns=["date", "rmm1", "rmm2", "mjo_phase", "mjo_amp"])
        rmm.to_csv(f"{OUT}/climate_mjo_daily.csv", index=False); print("MJO:", len(rmm), "days")
    except Exception as ex:
        print("!! MJO download failed:", repr(ex)[:150], "(model will run without it)")
    try:
        n34 = parse_psl_monthly(get_text("https://psl.noaa.gov/data/correlation/nina34.anom.data"), "nino34")
        dmi = parse_psl_monthly(get_text("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"), "iod_dmi")
        mon = n34.merge(dmi, on=["year", "month"], how="outer").sort_values(["year", "month"])
        mon.to_csv(f"{OUT}/climate_monthly.csv", index=False); print("ENSO/IOD:", len(mon), "months")
    except Exception as ex:
        print("!! ENSO/IOD download failed:", repr(ex)[:150], "(model will run without it)")

# %%
# ---- 7. Zip everything again -------------------------------------------------------------
import shutil
if os.path.exists(f"{OUT}/imd_raw"): shutil.rmtree(f"{OUT}/imd_raw")
if not MOCK:
    z = shutil.make_archive(OUT, "zip", OUT)
    print("Updated zip:", z, f"({os.path.getsize(z) / 1e6:.0f} MB)")
