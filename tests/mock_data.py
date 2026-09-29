"""Synthetic WB2 / IMD-like data for offline tests.

Truth: a smooth random rain/temperature field. Forecasts = truth + error that grows with lead,
plus injected "bust" episodes. IMD dates are deliberately shifted by one day to test alignment.
"""
import os, sys, re, shutil
import numpy as np, pandas as pd, xarray as xr

rng = np.random.default_rng(0)
LAT = np.round(np.arange(3.0, 45.01, 1.5), 3)
LON = np.round(np.arange(63.0, 105.01, 1.5), 3)
MOCK_YEARS = [int(y) for y in os.environ.get("MOCK_YEARS", "2016,2021").split(",")]
DAYS = pd.DatetimeIndex(sorted(set().union(*[set(pd.date_range(f"{y}-01-01", f"{y}-03-31")) for y in MOCK_YEARS])))
ALLDAYS = pd.DatetimeIndex(sorted(set().union(*[set(pd.date_range(f"{y}-01-01", f"{y}-04-15")) for y in MOCK_YEARS])))

def smooth(shape):
    x = rng.standard_normal(shape)
    for ax in (-1, -2):
        x = (np.roll(x, 1, ax) + x + np.roll(x, -1, ax)) / 3
    return x

TRUTH_R = {d: np.maximum(0, 8 * smooth((len(LAT), len(LON))) + 3) for d in ALLDAYS}  # mm/day
TRUTH_T = {d: 300 + 3 * smooth((len(LAT), len(LON))) for d in ALLDAYS}               # K
TRUTH_W = {d: 6 + 3 * np.abs(smooth((len(LAT), len(LON)))) for d in ALLDAYS}                    # m/s
BUSTY = set(rng.choice(ALLDAYS, int(0.12 * len(ALLDAYS)), replace=False))

def make_mock_wb2():
    inits = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in DAYS for h in (0, 12)])
    tds = pd.to_timedelta(np.arange(0, 241, 12), "h")
    levels = [200, 500, 700, 850]
    shp = (len(inits), len(tds), len(LAT), len(LON))
    rain = np.zeros(shp, "float32"); t2 = np.zeros(shp, "float32"); wind = np.zeros(shp, "float32")
    for i, it in enumerate(inits):
        for j, td in enumerate(tds):
            vt = it + td
            day_acc = (vt - pd.Timedelta(hours=24)).normalize()        # 24 h accumulation ending at vt
            lead_days = td / pd.Timedelta("1D")
            amp = 0.15 * lead_days * (4 if day_acc in BUSTY else 1)
            if day_acc in TRUTH_R:
                rain[i, j] = np.maximum(0, TRUTH_R[day_acc] * (1 + amp * smooth(shp[2:])) + amp * 3 * smooth(shp[2:])) / 1000
            if vt.normalize() in TRUTH_T:
                t2[i, j] = TRUTH_T[vt.normalize()] + 0.3 * lead_days * smooth(shp[2:])
                wind[i, j] = np.abs(TRUTH_W[vt.normalize()] + 0.4 * lead_days * (3 if vt.normalize() in BUSTY else 1) * smooth(shp[2:]))
    lv = lambda base: (base + rng.standard_normal((len(inits), len(tds), len(levels), len(LAT), len(LON))).astype("float32"))
    hres = xr.Dataset(
        {"total_precipitation_24hr": (("time", "prediction_timedelta", "latitude", "longitude"), rain),
         "2m_temperature": (("time", "prediction_timedelta", "latitude", "longitude"), t2),
         "mean_sea_level_pressure": (("time", "prediction_timedelta", "latitude", "longitude"),
                                     (100500 + 100 * rng.standard_normal(shp)).astype("float32")),
         "geopotential": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(55000)),
         "u_component_of_wind": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(0)),
         "v_component_of_wind": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(0)),
         "specific_humidity": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(0) * 1e-3 + 0.008),
         "temperature": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(260)),
         "vertical_velocity": (("time", "prediction_timedelta", "level", "latitude", "longitude"), lv(0) * 0.1),
         "10m_wind_speed": (("time", "prediction_timedelta", "latitude", "longitude"), wind)},
        coords={"time": inits, "prediction_timedelta": tds, "level": levels,
                "latitude": LAT[::-1] + 1e-7, "longitude": LON + 1e-7})   # descending + slightly-off float coords, like real WB2
    hres = hres.sortby("latitude", ascending=False)
    et = pd.DatetimeIndex(sorted(set().union(*[set(pd.date_range(f"{y}-01-01", f"{y}-04-20", freq="6h")) for y in MOCK_YEARS])))
    t2e = np.stack([TRUTH_T.get(t.normalize(), np.full((len(LAT), len(LON)), 300.0)) for t in et]).astype("float32")
    tpe = np.stack([TRUTH_R.get((t - pd.Timedelta(hours=24)).normalize(), np.zeros((len(LAT), len(LON)))) / 1000 for t in et]).astype("float32")
    w10 = np.stack([TRUTH_W.get(t.normalize(), np.full((len(LAT), len(LON)), 6.0)) for t in et]).astype("float32")
    era5 = xr.Dataset({"2m_temperature": (("time", "latitude", "longitude"), t2e),
                       "10m_wind_speed": (("time", "latitude", "longitude"), w10),
                       "total_precipitation_24hr": (("time", "latitude", "longitude"), tpe)},
                      coords={"time": et, "latitude": LAT, "longitude": LON})
    return hres, era5

def make_mock_imd(years):
    flat = np.round(np.arange(6.5, 38.51, 0.25), 3); flon = np.round(np.arange(66.5, 100.01, 0.25), 3)
    land = ((flon[None] >= 68) & (flon[None] <= 97) & (flat[:, None] >= 8) & (flat[:, None] <= 37)
            & ~((flat[:, None] < 20) & ((flon[None] < 73) | (flon[None] > 86))))
    ia = np.abs(flat[:, None] - LAT[None]).argmin(1); io = np.abs(flon[:, None] - LON[None]).argmin(1)
    data = []
    for d in ALLDAYS:
        x = TRUTH_R[d][np.ix_(ia, io)] + 0.2 * rng.standard_normal((len(flat), len(flon)))
        data.append(np.where(land, np.maximum(x, 0), np.nan))
    # IMD labels the day one day LATER than the UTC day (tests the automatic alignment)
    return xr.DataArray(np.array(data, "float32"), dims=("time", "lat", "lon"),
                        coords={"time": ALLDAYS + pd.Timedelta(days=1), "lat": flat, "lon": flon}, name="rain")


def era5_coarse_mock():
    et = pd.DatetimeIndex(sorted(set().union(*[set(pd.date_range(f"{y}-01-01", f"{y}-04-20", freq="6h")) for y in MOCK_YEARS])))
    la, lo = LAT[::3], LON[::3]
    z = (55000 + 300 * rng.standard_normal((len(et), 1, len(la), len(lo)))).astype("float32")
    return xr.Dataset({"geopotential": (("time", "level", "latitude", "longitude"), z)},
                      coords={"time": et, "level": [500], "latitude": la, "longitude": lo})

def make_mock_imd_tmax(years):
    flat = np.arange(7.5, 37.51, 1.0); flon = np.arange(67.5, 97.51, 1.0)
    ia = np.abs(flat[:, None] - LAT[None]).argmin(1); io = np.abs(flon[:, None] - LON[None]).argmin(1)
    data = [TRUTH_T[d][np.ix_(ia, io)] - 273.15 + 3 + 0.3 * rng.standard_normal((len(flat), len(flon))) for d in ALLDAYS]
    return xr.DataArray(np.array(data, "float32"), dims=("time", "lat", "lon"),
                        coords={"time": ALLDAYS, "lat": flat, "lon": flon}, name="tmax")
