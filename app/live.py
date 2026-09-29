"""BustRadar live mode: download today's ECMWF forecast and turn it into BustRadar input.

ECMWF publishes its IFS (HRES) forecasts free of charge ("open data", CC-BY-4.0): 0.25° global fields,
00 UTC run out to 10 days. This script
  1. downloads the latest --runs daily 00 UTC runs (4 = today + 3 earlier runs, needed for the
     "do recent runs agree?" features),
  2. converts them exactly like the WeatherBench-2 training data (same grid, same variables, same units),
  3. optionally downloads IMD real-time rainfall and verifies earlier live runs (for the report card
     and the "recent errors" features),
  4. writes  <data>/maps/fc_live.nc, <data>/maps/fcx_live.nc, <data>/maps/obs_live.nc and
     <data>/regions_live.parquet  next to the archive data. Nothing in the archive is changed.

Then run notebook 02 with MODE = "infer" and notebook 04 (or app/build_bundle.py).

    pip install ecmwf-opendata cfgrib eccodes xarray pandas numpy scipy imdlib
    python app/live.py                                  # latest run + 3 earlier runs
    python app/live.py --date 2026-09-28 --runs 4       # a specific run date
    python app/live.py --source aws                     # AWS mirror (keeps older runs than ECMWF's own server)
    python app/live.py --selftest                       # check the conversion offline with synthetic fields

Honest caveats (also shown on the dashboard):
  * The IFS model has been upgraded since 2022 (the last training year), so its error behaviour is not identical.
  * Features that need observations (recent errors) are empty until IMD real-time rainfall is available.
"""
import argparse, glob, json, os, sys, time, warnings, datetime as dt
warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="All-NaN slice")
import numpy as np
import pandas as pd
import xarray as xr

HERE = os.path.dirname(os.path.abspath(globals().get("__file__", "./live.py")))
LEADS = np.arange(1, 11)
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJAS", 7: "JJAS", 8: "JJAS", 9: "JJAS", 10: "ON", 11: "ON"}
COARSE = 5.625                                   # WB2 64x32 grid used for the upper air in training
COARSE_LAT = -87.1875 + COARSE * np.arange(32)
COARSE_LON = COARSE * np.arange(64)

SFC = {"tp": "rain", "2t": "t2m", "msl": "mslp", "10u": "u10", "10v": "v10"}
PL_PARAMS, PL_LEVELS = ["gh", "u", "v", "q", "t", "w"], [200, 500, 700, 850]


# ------------------------------------------------------------------------------------------ helpers
def find_data():
    c = (glob.glob(os.path.join(HERE, "..", "data", "bustradar_data", "grid_meta.nc"))
         + glob.glob("/kaggle/working/bustradar_data/grid_meta.nc") + glob.glob("/kaggle/input/**/grid_meta.nc", recursive=True)
         + glob.glob("./**/bustradar_data/grid_meta.nc", recursive=True))
    if not c:
        sys.exit("Could not find bustradar_data (grid_meta.nc). Pass --data path/to/bustradar_data")
    return os.path.dirname(c[0])


def overlap_weights(src_centres, src_width, dst_centres, dst_width):
    """Conservative 1-D weights: fraction of each target cell covered by each source cell."""
    s0, s1 = src_centres - src_width / 2, src_centres + src_width / 2
    d0, d1 = dst_centres - dst_width / 2, dst_centres + dst_width / 2
    ov = np.clip(np.minimum(d1[:, None], s1[None, :]) - np.maximum(d0[:, None], s0[None, :]), 0, None)
    return ov / np.maximum(ov.sum(1, keepdims=True), 1e-12)


def regrid(a, lat, lon, dst_lat, dst_lon, dst_res, src_res=0.25):
    """(..., lat, lon) on the 0.25° grid -> conservative average on the target grid."""
    Wa = overlap_weights(lat, src_res, dst_lat, dst_res)
    Wo = overlap_weights(lon, src_res, dst_lon, dst_res)
    return np.einsum("ia,...ab,jb->...ij", Wa, a, Wo, optimize=True)


def to_training_grid(a, lat, lon, TLAT, TLON, coarse):
    """Fine variables: 0.25° -> 1.5° (as WB2 240x121 conservative).
    Upper air: 0.25° -> 5.625° (as WB2 64x32 conservative) -> linear interpolation to 1.5°, as in notebook 01."""
    if not coarse:
        return regrid(a, lat, lon, TLAT, TLON, 1.5)
    clat = COARSE_LAT[(COARSE_LAT >= TLAT[0] - 6 - 1e-6) & (COARSE_LAT <= TLAT[-1] + 6 + 1e-6)]
    clon = COARSE_LON[(COARSE_LON >= TLON[0] - 6 - 1e-6) & (COARSE_LON <= TLON[-1] + 6 + 1e-6)]
    c = regrid(a, lat, lon, clat, clon, COARSE)
    lead = a.shape[:-2]
    da = xr.DataArray(c.reshape((-1, len(clat), len(clon))), dims=("k", "latitude", "longitude"),
                      coords={"latitude": clat, "longitude": clon})
    out = da.interp(latitude=TLAT, longitude=TLON, kwargs={"fill_value": None}).values
    return out.reshape(lead + (len(TLAT), len(TLON)))


# ------------------------------------------------------------------------------------------ download
def steps_needed():
    s = set()
    for L in LEADS:
        s |= {24 * L - 24, 24 * L - 18, 24 * L - 12, 24 * L - 6, 24 * L}
    return sorted(x for x in s if x >= 0)


def grib_engine():
    """The cfgrib backend class itself. Passing the class (not the name "cfgrib") also works when cfgrib was
    pip-installed after xarray was imported, e.g. in the same Kaggle session."""
    try:
        from cfgrib.xarray_plugin import CfGribBackendEntrypoint
        return CfGribBackendEntrypoint
    except Exception:
        try:
            from xarray.backends import plugins
            plugins.list_engines.cache_clear()
        except Exception:
            pass
        return "cfgrib"


def download_run(client, date, cache):
    """Returns {name: DataArray(step, [level,] latitude, longitude)} for one 00 UTC run, cropped to India + margin."""
    os.makedirs(cache, exist_ok=True)
    tag = date.strftime("%Y%m%d")
    files = {"sfc": os.path.join(cache, f"ifs_{tag}_sfc.grib2"), "pl": os.path.join(cache, f"ifs_{tag}_pl.grib2")}
    reqs = {"sfc": dict(param=list(SFC), step=steps_needed()),
            "pl": dict(param=PL_PARAMS, levelist=PL_LEVELS, step=[24 * int(L) for L in LEADS])}
    for k, req in reqs.items():
        if os.path.exists(files[k]) and os.path.getsize(files[k]) > 1e6:
            continue
        for attempt in range(1, 4):
            try:
                t0 = time.time()
                client.retrieve(date=date.strftime("%Y-%m-%d"), time=0, stream="oper", type="fc",
                                target=files[k] + ".part", **req)
                os.replace(files[k] + ".part", files[k])
                print(f"   {k}: {os.path.getsize(files[k]) / 1e6:.0f} MB in {time.time() - t0:.0f}s", flush=True)
                break
            except Exception as e:
                print(f"   {k}: attempt {attempt} failed: {repr(e)[:160]}")
                if attempt == 3:
                    raise
                time.sleep(15 * attempt)
    out = {}
    for k in ("sfc", "pl"):
        params = list(SFC) if k == "sfc" else PL_PARAMS
        for sn in params:
            ds = xr.open_dataset(files[k], engine=grib_engine(),
                                 backend_kwargs={"filter_by_keys": {"shortName": sn}, "indexpath": ""})
            da = ds[list(ds.data_vars)[0]]
            if "isobaricInhPa" in da.dims:
                da = da.rename({"isobaricInhPa": "level"})
            lon = da.longitude.values
            if lon.max() > 180:                                   # 0..360 -> -180..180 for a clean crop
                da = da.assign_coords(longitude=((lon + 180) % 360) - 180).sortby("longitude")
            da = da.sel(latitude=slice(None, None)).sortby("latitude")
            da = da.sel(latitude=slice(-10, 55), longitude=slice(45, 125)).load()
            da = da.assign_coords(step=(pd.to_timedelta(da.step.values) / pd.Timedelta("1h")).astype(int))
            out[sn] = da
            ds.close()
    return out


# ------------------------------------------------------------------------------------------ convert
def convert(raw, TLAT, TLON):
    """raw fields of ONE run -> (fc variables, fcx variables), each (lead, lat, lon) float32, training units."""
    lat, lon = raw["tp"].latitude.values, raw["tp"].longitude.values
    at = lambda sn, steps, **sel: raw[sn].sel(step=steps, **sel).values
    fine = lambda a: to_training_grid(a, lat, lon, TLAT, TLON, coarse=False)
    crs = lambda a: to_training_grid(a, lat, lon, TLAT, TLON, coarse=True)
    d24 = [24 * int(L) for L in LEADS]

    tp = at("tp", [24 * int(L) - 24 for L in LEADS] + d24).astype("float64")
    n = len(LEADS)
    rain = np.clip((tp[n:] - tp[:n]) * 1000.0, 0, None)                    # m accumulated -> mm per forecast day
    t2m = at("2t", [24 * int(L) - 12 for L in LEADS])                       # 12 UTC of day L
    tmax = np.maximum(at("2t", [24 * int(L) - 18 for L in LEADS]), t2m)    # max of 06 and 12 UTC
    mslp = at("msl", d24) / 100.0                                           # Pa -> hPa
    wmax = None
    for k in (18, 12, 6, 0):                                                # max of 06/12/18/24 UTC wind speed
        st = [24 * int(L) - k for L in LEADS]
        sp = np.hypot(at("10u", st), at("10v", st))
        wmax = sp if wmax is None else np.maximum(wmax, sp)
    lev = lambda sn, p: at(sn, d24, level=p)

    fc = {"rain": fine(rain), "t2m": fine(t2m), "mslp": fine(mslp),
          "z500": crs(lev("gh", 500)),                                      # gh is already geopotential height (gpm)
          "u850": crs(lev("u", 850)), "v850": crs(lev("v", 850)), "q700": crs(lev("q", 700) * 1000.0)}
    fcx = {"wind10max": fine(wmax), "tmax": fine(tmax),
           "u200": crs(lev("u", 200)), "v200": crs(lev("v", 200)),
           "t500": crs(lev("t", 500)), "t700": crs(lev("t", 700)), "t850": crs(lev("t", 850)),
           "w500": crs(lev("w", 500)), "q850": crs(lev("q", 850) * 1000.0)}
    cast = lambda d: {k: v.astype("float32") for k, v in d.items()}
    return cast(fc), cast(fcx)


def to_dataset(runs, TLAT, TLON):
    inits = pd.DatetimeIndex(sorted(runs))
    names = list(next(iter(runs.values())))
    return xr.Dataset({k: (("init", "lead", "lat", "lon"), np.stack([runs[i][k] for i in inits]))
                       for k in names}, coords={"init": inits, "lead": LEADS, "lat": TLAT, "lon": TLON})


def merge_keep(path, new, keep):
    if os.path.exists(path):
        with xr.open_dataset(path) as old:
            old = old.load()
        old = old.sel(init=~old.init.isin(new.init.values))
        new = xr.concat([old, new], "init").sortby("init")
    new = new.isel(init=slice(-keep, None))
    new.to_netcdf(path + ".tmp"); os.replace(path + ".tmp", path)
    return new


# ------------------------------------------------------------------------------------------ verify (IMD)
def imd_realtime(start, end, cache, TLAT, TLON):
    """IMD real-time gridded rainfall (0.25°, ~1 day delay) -> 1.5° block average, date = IMD date."""
    import imdlib as imd
    d = os.path.join(cache, "imd_rt"); os.makedirs(d, exist_ok=True)
    data = imd.get_real_data("rain", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), file_dir=d)
    x = data.get_xarray(); x = x[list(x.data_vars)[0]].where(lambda v: v > -998)
    la, lo = x.lat.values, x.lon.values
    a = x.transpose("time", "lat", "lon").values.astype("float64")
    Wa, Wo = overlap_weights(la, 0.25, TLAT, 1.5), overlap_weights(lo, 0.25, TLON, 1.5)
    ok = np.isfinite(a)
    s = np.einsum("ia,tab,jb->tij", (Wa > 0).astype(float), np.where(ok, a, 0), (Wo > 0).astype(float), optimize=True)
    c = np.einsum("ia,tab,jb->tij", (Wa > 0).astype(float), ok.astype(float), (Wo > 0).astype(float), optimize=True)
    tot = (Wa > 0).sum(1)[:, None] * (Wo > 0).sum(1)[None, :]
    mean = np.where(c >= 0.5 * tot, s / np.maximum(c, 1), np.nan)
    return xr.DataArray(mean.astype("float32"), dims=("date", "lat", "lon"),
                        coords={"date": pd.DatetimeIndex(x.time.values).normalize(), "lat": TLAT, "lon": TLON})


def best_shift(fc, obs, land):
    """Same idea as notebook 01: which IMD date labelling best matches Day-1/Day-2 forecasts (space + time)."""
    sc = {}
    for s in (-1, 0, 1):
        o = obs.assign_coords(date=obs.date - pd.Timedelta(days=s))
        xs, ys = [], []
        for i in fc.init.values:
            for L in (1, 2):
                v = pd.Timestamp(i) + pd.Timedelta(days=L - 1)
                if v in o.date.values:
                    xs.append(fc["rain"].sel(init=i, lead=L).values[land]); ys.append(o.sel(date=v).values[land])
        if xs:
            x, y = np.concatenate(xs), np.concatenate(ys); ok = np.isfinite(x) & np.isfinite(y)
            sc[s] = np.corrcoef(np.log1p(x[ok]), np.log1p(y[ok]))[0, 1] if ok.sum() > 50 else np.nan
    good = {k: v for k, v in sc.items() if np.isfinite(v)}
    return (max(good, key=good.get) if good else 0), sc


# ------------------------------------------------------------------------------------------ region rows
def region_rows(fc, fcx, meta, obs_rain=None):
    """Same columns as notebook 01's regions table (observations filled only where verified)."""
    REG = json.loads(meta.attrs["regions"]); RID = meta.region_id.values
    inits = pd.DatetimeIndex(fc.init.values)
    valid = inits.values[:, None] + (LEADS - 1)[None, :] * np.timedelta64(1, "D")
    base = pd.DataFrame({"init": np.repeat(inits.values, len(LEADS)), "lead": np.tile(LEADS, len(inits)),
                         "valid_date": valid.ravel()})
    ob = None
    if obs_rain is not None:
        pos = pd.Index(pd.DatetimeIndex(obs_rain.date.values)).get_indexer(valid.ravel())
        a = obs_rain.values
        ob = np.full((valid.size,) + a.shape[1:], np.nan); ob[pos >= 0] = a[pos[pos >= 0]]
        ob = ob.reshape(len(inits), len(LEADS), *a.shape[1:])
    rows = []
    for r, name in enumerate(REG):
        m = RID == r
        d = base.copy(); d["region"] = name
        for v in fc.data_vars:
            d[f"fc_{v}"] = np.nanmean(fc[v].values[:, :, m], axis=2).ravel()
        d["fc_rain_max"] = np.nanmax(fc["rain"].values[:, :, m], axis=2).ravel()
        if ob is not None:
            o = ob[:, :, m]; f = fc["rain"].values[:, :, m]
            with np.errstate(all="ignore"):
                d["obs_rain"] = np.where(np.isfinite(o).any(2), np.nanmean(o, 2), np.nan).ravel()
                d["rain_rmse"] = np.where(np.isfinite(o).any(2), np.sqrt(np.nanmean((f - o) ** 2, 2)), np.nan).ravel()
        else:
            d["obs_rain"], d["rain_rmse"] = np.nan, np.nan
        rows.append(d)
    df = pd.concat(rows, ignore_index=True)
    df["init"] = pd.to_datetime(df["init"]); df["valid_date"] = pd.to_datetime(df["valid_date"])
    df["rain_err"] = df["fc_rain"] - df["obs_rain"]
    fcols = [c for c in df.columns if c.startswith("fc_")]
    prev = df[["init", "lead", "region"] + fcols].copy()
    prev["init"] += pd.Timedelta(days=1); prev["lead"] -= 1
    df = df.merge(prev.rename(columns={c: c + "_prev" for c in fcols}), on=["init", "lead", "region"], how="left")
    for c in fcols:
        df[c.replace("fc_", "jump_")] = df[c] - df[c + "_prev"]
    df = df.drop(columns=[c + "_prev" for c in fcols])
    df["month"] = df["valid_date"].dt.month; df["season"] = df["month"].map(SEASON); df["split"] = "live"
    return df


def save_table(df, stem):
    try:
        df.to_parquet(stem + ".parquet", index=False); return stem + ".parquet"
    except Exception:
        df.to_csv(stem + ".csv.gz", index=False); return stem + ".csv.gz"


def refresh_climate(data):
    """Update MJO (BoM) and ENSO/IOD (NOAA PSL) so the climate-driver features are current."""
    import urllib.request
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (BustRadar)"}),
                                           timeout=60).read().decode("utf-8", "ignore")
    try:
        rows = []
        for line in get("http://www.bom.gov.au/climate/mjo/graphics/rmm.74toRealtime.txt").splitlines():
            p = line.replace(",", " ").split()
            if len(p) >= 7 and p[0].isdigit() and len(p[0]) == 4 and abs(float(p[3])) < 900:
                rows.append((f"{p[0]}-{int(p[1]):02d}-{int(p[2]):02d}", float(p[3]), float(p[4]), int(float(p[5])), float(p[6])))
        pd.DataFrame(rows, columns=["date", "rmm1", "rmm2", "mjo_phase", "mjo_amp"]).to_csv(f"{data}/climate_mjo_daily.csv", index=False)
        print("MJO updated to", rows[-1][0])
    except Exception as e:
        print("MJO update failed (old file kept):", repr(e)[:120])
    try:
        def psl(txt, name):
            out = []
            for line in txt.splitlines():
                p = line.split()
                if len(p) == 13 and p[0].isdigit() and len(p[0]) == 4:
                    out += [(int(p[0]), m, float(v)) for m, v in enumerate(p[1:], 1) if float(v) > -90]
            return pd.DataFrame(out, columns=["year", "month", name])
        mon = psl(get("https://psl.noaa.gov/data/correlation/nina34.anom.data"), "nino34").merge(
            psl(get("https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"), "iod_dmi"), on=["year", "month"], how="outer")
        mon.sort_values(["year", "month"]).to_csv(f"{data}/climate_monthly.csv", index=False); print("ENSO/IOD updated")
    except Exception as e:
        print("ENSO/IOD update failed (old file kept):", repr(e)[:120])


# ------------------------------------------------------------------------------------------ main
def synthetic_run(date):
    """Fake 0.25° fields with realistic magnitudes, for --selftest (no network)."""
    rs = np.random.default_rng(int(date.strftime("%Y%m%d")))
    lat, lon = np.arange(-10, 55.01, 0.25), np.arange(45, 125.01, 0.25)
    st = steps_needed(); st24 = [24 * int(L) for L in LEADS]
    mk = lambda steps, base, amp, **kw: xr.DataArray(
        base + amp * rs.standard_normal((len(steps), len(lat), len(lon))), dims=("step", "latitude", "longitude"),
        coords={"step": steps, "latitude": lat, "longitude": lon})
    tp = np.cumsum(np.clip(rs.gamma(0.6, 0.004, (len(st), len(lat), len(lon))), 0, None), axis=0)
    raw = {"tp": xr.DataArray(tp, dims=("step", "latitude", "longitude"), coords={"step": st, "latitude": lat, "longitude": lon}),
           "2t": mk(st, 303, 3), "msl": mk(st, 100800, 300), "10u": mk(st, 0, 5), "10v": mk(st, 0, 5)}
    base = {"gh": {200: 12400, 500: 5870, 700: 3150, 850: 1500}, "u": {200: 15, 500: 5, 700: 3, 850: 5},
            "v": {200: 0, 500: 0, 700: 0, 850: 2}, "q": {200: 1e-5, 500: 2e-3, 700: 6e-3, 850: 1.2e-2},
            "t": {200: 220, 500: 267, 700: 283, 850: 293}, "w": {200: 0, 500: -0.05, 700: -0.05, 850: -0.02}}
    for sn, lv in base.items():
        a = np.stack([np.stack([lv[p] + (abs(lv[p]) * 0.02 + 1e-4) * rs.standard_normal((len(lat), len(lon))) for p in PL_LEVELS])
                      for _ in st24])
        raw[sn] = xr.DataArray(a, dims=("step", "level", "latitude", "longitude"),
                               coords={"step": st24, "level": PL_LEVELS, "latitude": lat, "longitude": lon})
    return raw


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="bustradar_data folder (grid_meta.nc, maps/, regions.parquet)")
    ap.add_argument("--date", help="run date YYYY-MM-DD (default: latest available)")
    ap.add_argument("--runs", type=int, default=4, help="number of daily runs to fetch, ending at --date")
    ap.add_argument("--keep", type=int, default=60, help="how many live runs to keep (older are dropped)")
    ap.add_argument("--source", default="ecmwf", help="ecmwf | aws | azure")
    ap.add_argument("--cache", default=None, help="folder for downloaded GRIB files")
    ap.add_argument("--no-verify", action="store_true", help="skip IMD real-time rainfall")
    ap.add_argument("--no-climate", action="store_true", help="skip MJO/ENSO/IOD refresh")
    ap.add_argument("--selftest", action="store_true", help="synthetic fields, no network (checks the pipeline)")
    a = ap.parse_args(globals().get("LIVE_ARGS"))

    data = a.data or find_data()
    if not os.access(data, os.W_OK):
        # e.g. a read-only Kaggle input dataset: make a writable folder of links next to the notebook
        mirror = "/kaggle/working/bustradar_data" if os.path.exists("/kaggle/working") else os.path.abspath("bustradar_data")
        os.makedirs(os.path.join(mirror, "maps"), exist_ok=True)
        for f in glob.glob(os.path.join(data, "*")) + glob.glob(os.path.join(data, "maps", "*")):
            dst = os.path.join(mirror, os.path.relpath(f, data))
            if os.path.isfile(f) and not os.path.exists(dst):
                os.symlink(os.path.abspath(f), dst)
        print(f"{data} is read-only: working in {mirror} (links to the original files)")
        data = mirror
    cache = a.cache or os.path.join(data, "..", "live_cache")
    with xr.open_dataset(os.path.join(data, "grid_meta.nc")) as m:
        meta = m.load()
    TLAT, TLON = meta.lat.values, meta.lon.values

    if a.selftest:
        client, last = None, pd.Timestamp(a.date or "2026-09-28")
    else:
        try:
            from ecmwf.opendata import Client
        except ImportError:
            sys.exit("pip install ecmwf-opendata cfgrib eccodes")
        client = Client(source=a.source, model="ifs", resol="0p25")
        if a.date:
            last = pd.Timestamp(a.date)
        else:
            last = pd.Timestamp(client.latest(type="fc", stream="oper", step=240, time=0)).normalize()
    dates = pd.date_range(end=last, periods=a.runs, freq="D")
    print(f"Live runs: {[str(d.date()) for d in dates]}  | data: {os.path.abspath(data)}")

    fc_runs, fcx_runs = {}, {}
    for d in dates:
        t0 = time.time()
        try:
            raw = synthetic_run(d) if a.selftest else download_run(client, d, cache)
        except Exception as e:
            print(f"{d.date()}: skipped ({repr(e)[:160]})"); continue
        fc_runs[d], fcx_runs[d] = convert(raw, TLAT, TLON)
        print(f"{d.date()}: converted ({time.time() - t0:.0f}s) | India land rain Day1 "
              f"{np.nanmean(fc_runs[d]['rain'][0][meta.land.values.astype(bool)]):.1f} mm/day")
    if not fc_runs:
        sys.exit("No runs downloaded.")
    os.makedirs(os.path.join(data, "maps"), exist_ok=True)
    for prefix, runs in (("fc", fc_runs), ("fcx", fcx_runs)):    # same variables as the archive files
        arch = sorted(glob.glob(os.path.join(data, "maps", f"{prefix}_[0-9]*.nc")))
        if arch:
            with xr.open_dataset(arch[-1]) as ref:
                keepv = set(ref.data_vars)
            for d in runs:
                runs[d] = {k: v for k, v in runs[d].items() if k in keepv}
    fc = merge_keep(os.path.join(data, "maps", "fc_live.nc"), to_dataset(fc_runs, TLAT, TLON), a.keep)
    fcx = merge_keep(os.path.join(data, "maps", "fcx_live.nc"), to_dataset(fcx_runs, TLAT, TLON), a.keep)

    obs_rain = None
    if not a.no_verify and not a.selftest:
        try:
            start = pd.Timestamp(fc.init.values[0]) - pd.Timedelta(days=8)
            o = imd_realtime(start, pd.Timestamp.now().normalize() - pd.Timedelta(days=1), cache, TLAT, TLON)
            s, sc = best_shift(fc, o, meta.land.values.astype(bool))
            obs_rain = o.assign_coords(date=o.date - pd.Timedelta(days=s))
            print(f"IMD real-time rain: {o.date.size} days (shift {s}, correlations {({k: round(v, 2) for k, v in sc.items()})})")
            # observation map in the same layout as the archive (other variables left empty)
            arch = sorted(glob.glob(os.path.join(data, "maps", "obs_[0-9]*.nc")))
            ov = list(xr.open_dataset(arch[-1]).data_vars) if arch else ["rain"]
            ds = xr.Dataset({v: obs_rain if v == "rain" else xr.full_like(obs_rain, np.nan) for v in ov})
            ds.to_netcdf(os.path.join(data, "maps", "obs_live.nc.tmp"))
            os.replace(os.path.join(data, "maps", "obs_live.nc.tmp"), os.path.join(data, "maps", "obs_live.nc"))
        except Exception as e:
            print("IMD real-time rainfall not available, live runs stay unverified:", repr(e)[:160])
    rows = region_rows(fc, fcx, meta, obs_rain)
    print("Saved", save_table(rows, os.path.join(data, "regions_live")), rows.shape,
          f"| verified rows: {int(rows.obs_rain.notna().sum())}")
    if not a.no_climate and not a.selftest:
        refresh_climate(data)
    json.dump({"source": f"ECMWF open data IFS 0.25° ({a.source})", "runs": [str(pd.Timestamp(i).date()) for i in fc.init.values],
               "downloaded": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "selftest": a.selftest},
              open(os.path.join(data, "live_info.json"), "w"), indent=1)
    print("\nNext: notebook 02 with MODE = 'infer'  ->  notebook 04 (or python app/build_bundle.py)")
