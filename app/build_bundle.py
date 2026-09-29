"""Build the BustRadar dashboard from the notebook-02 outputs.

    python app/build_bundle.py --models path/to/bustradar_models [--out app/dist]

Writes:
  dist/bundle.json               compact data for the API server
  dist/bustradar_dashboard.html  ONE self-contained file: double-click to open, works offline,
                                 or upload to GitHub Pages for a live link.
Needs: pandas (+ pyarrow for .parquet), numpy, and xarray or scipy to read grid_meta.nc.
"""
import argparse, json, os, glob, datetime as dt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = ["rain", "heat", "wind", "z500"]
TYPE_LABELS = {"rain": "Rain", "heat": "Heat (Tmax)", "wind": "Wind", "z500": "500 hPa pattern", "any": "Any"}
SYSTEMS = ["depression", "cyclone", "wd", "heatwave", "active", "break"]
SYSTEM_LABELS = {"depression": "Monsoon depression", "cyclone": "Cyclonic system", "wd": "Western disturbance",
                 "heatwave": "Heat wave", "active": "Active monsoon", "break": "Monsoon break"}
# Hindi labels for the Hindi bulletin
REGION_HI = {"Himalayan WH": "पश्चिमी हिमालय", "NE India": "पूर्वोत्तर भारत", "NW India": "उत्तर-पश्चिम भारत",
             "East India": "पूर्वी भारत", "West Coast": "पश्चिमी तट", "Central India": "मध्य भारत",
             "S. Peninsula": "दक्षिण प्रायद्वीप"}
TYPE_LABELS_HI = {"rain": "वर्षा", "heat": "ताप (अधिकतम तापमान)", "wind": "पवन", "z500": "500 hPa पैटर्न", "any": "कोई भी"}
SYSTEM_LABELS_HI = {"depression": "मानसून अवदाब", "cyclone": "चक्रवाती प्रणाली", "wd": "पश्चिमी विक्षोभ",
                    "heatwave": "लू (हीट वेव)", "active": "सक्रिय मानसून", "break": "मानसून विराम"}
ISLANDS = {"Andaman & Nicobar Islands", "Lakshadweep"}       # outside the 1.5° land regions: drawn, not scored
EVENTS = [
    ("Kerala floods", "West Coast", "2018-08-14", "2018-08-17", "rain"),
    ("Cyclone Fani", "East India", "2019-05-02", "2019-05-04", "any"),
    ("Mumbai extreme rain", "West Coast", "2019-07-01", "2019-07-02", "rain"),
    ("Cyclone Amphan", "East India", "2020-05-19", "2020-05-21", "any"),
    ("Hyderabad floods", "S. Peninsula", "2020-10-13", "2020-10-14", "rain"),
    ("Cyclone Tauktae", "West Coast", "2021-05-15", "2021-05-17", "any"),
    ("Uttarakhand extreme rain", "Himalayan WH", "2021-10-17", "2021-10-19", "rain"),
    ("NW India heat wave", "NW India", "2022-04-26", "2022-04-30", "heat"),
    ("Assam/Meghalaya floods", "NE India", "2022-06-14", "2022-06-17", "rain"),
]


def read_table(folder, stem):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv.gz", pd.read_csv), (".csv", pd.read_csv)):
        p = os.path.join(folder, stem + ext)
        if os.path.exists(p):
            try:
                return fn(p)
            except pd.errors.EmptyDataError:
                return None
    return None


def read_grid(folder):
    p = os.path.join(folder, "grid_meta.nc")
    try:
        import xarray as xr
        g = xr.open_dataset(p).load()
        return (g.lat.values.tolist(), g.lon.values.tolist(), g.region_id.values.astype(int).tolist(),
                g.land.values.astype(int).tolist(), json.loads(g.attrs["regions"]))
    except Exception:
        from scipy.io import netcdf_file
        with netcdf_file(p, "r", mmap=False) as f:
            regions = json.loads(f.regions.decode() if isinstance(f.regions, bytes) else f.regions)
            return (f.variables["lat"][:].tolist(), f.variables["lon"][:].tolist(),
                    f.variables["region_id"][:].astype(int).tolist(), f.variables["land"][:].astype(int).tolist(), regions)


def pct(x):
    return np.where(np.isfinite(x), np.round(100 * x), -1).astype(int)


def read_unet(unet_path, dates, leads, land):
    """Grid-level U-Net probabilities for land cells, packed as base64 uint8 (255 = missing)."""
    import base64
    try:
        import xarray as xr
        u = xr.open_dataset(unet_path).load()
    except Exception as e:
        print("U-Net layer skipped:", e); return None
    land = np.array(land, bool); cells = np.flatnonzero(land.ravel())
    ui = pd.Index(pd.DatetimeIndex(u.init.values).normalize())
    out = np.full((len(dates), len(leads), len(cells)), 255, dtype=np.uint8)
    pv = u["p"].transpose("init", "lead", "lat", "lon").values
    for k, d in enumerate(dates):
        j = ui.get_indexer([pd.Timestamp(d)])[0]
        if j >= 0:
            out[k] = np.clip(pv[j].reshape(len(leads), -1)[:, cells], 0, 100).astype(np.uint8)
    metrics = None
    mp = os.path.join(os.path.dirname(unet_path), "unet_metrics.json")
    if os.path.exists(mp):
        metrics = json.load(open(mp))
    return {"cells": cells.tolist(), "p_b64": base64.b64encode(out.tobytes()).decode(), "metrics": metrics}


def read_states(rid, land):
    """State outlines (DataMeet / Survey of India) + how much of each state lies in each forecast region."""
    p = os.path.join(HERE, "states_india.json")
    if not os.path.exists(p):
        return None
    S = json.load(open(p, encoding="utf-8"))
    rid = np.array(rid); nla, nlo = rid.shape
    reg_cells = np.argwhere(rid >= 0)
    out = []
    for st in S["states"]:
        wts, cells, cover, total = {}, [], 0.0, 0.0
        for i, j, w in st["cells"]:
            total += w
            if rid[i][j] >= 0:
                wts[int(rid[i][j])] = wts.get(int(rid[i][j]), 0) + w; cover += w
            if land[i][j]:
                cells.append([i, j, w])
        scored = st["name"] not in ISLANDS
        if scored and not wts:                                  # tiny UT or area outside the region boxes: nearest region
            ci, cj = st["centroid_cell"]
            k = np.argmin(((reg_cells - [ci, cj]) ** 2).sum(1)); wts = {int(rid[tuple(reg_cells[k])]): 1.0}
        tw = sum(wts.values()) or 1
        out.append({"name": st["name"], "name_hi": st["name_hi"], "label": st["label"], "outline": st["outline"],
                    "scored": scored, "regions": [[r, round(w / tw, 3)] for r, w in sorted(wts.items(), key=lambda x: -x[1])],
                    "coverage": round(cover / total, 2) if total else 0, "cells": cells})
    return {"source": S["source"], "india_outline": S["india_outline"], "states": out}


def build(models_dir, years=None, unet_path=None):
    pred = read_table(models_dir, "predictions")
    if pred is None:
        raise FileNotFoundError(f"predictions.parquet not found in {models_dir}")
    pred["init"] = pd.to_datetime(pred["init"]); pred["valid_date"] = pd.to_datetime(pred["valid_date"])
    lat, lon, rid, land, regions = read_grid(models_dir)
    R = len(regions); leads = sorted(pred["lead"].unique().tolist()); NL = len(leads)
    types = [t for t in TYPES if f"p_bust_{t}" in pred]

    # dashboard covers the validation + test years (the honest, not-trained-on period)
    if years is None:
        years = sorted(pred.loc[pred["split"].isin(["val", "test", "live"]), "init"].dt.year.unique().tolist())
    sub = pred[pred["init"].dt.year.isin(years)].copy()
    dates = sorted(sub["init"].dt.normalize().unique())
    full = pd.MultiIndex.from_product([dates, leads, regions], names=["init", "lead", "region"])
    sub = sub.set_index(["init", "lead", "region"]).reindex(full).reset_index()

    reasons_list, reasons_hi, reason_idx = [], [], {}
    def ridx(s, h):
        if not isinstance(s, str) or not s:
            return -1
        h = h if isinstance(h, str) and h else s
        if (s, h) not in reason_idx:
            reason_idx[(s, h)] = len(reasons_list); reasons_list.append(s); reasons_hi.append(h)
        return reason_idx[(s, h)]

    cols = {"p": pct(sub["p_bust"].values)}
    for t in types:
        cols[f"p_{t}"] = pct(sub[f"p_bust_{t}"].values)
    act = np.zeros(len(sub), dtype=int)                     # bitmask of real busts: bit k = TYPES[k]
    for k, t in enumerate(types):
        if f"bust_{t}" in sub:
            act |= (sub[f"bust_{t}"].fillna(0).astype(int).values << k)
    cols["actual"] = np.where(sub["bust"].isna(), -1, act).astype(int)
    sysm = np.zeros(len(sub), dtype=int)
    for k, s in enumerate(SYSTEMS):
        if f"sys_{s}" in sub:
            sysm |= (sub[f"sys_{s}"].fillna(0).astype(int).values << k)
    cols["sys"] = sysm
    en = sub["reasons"] if "reasons" in sub else pd.Series([""] * len(sub))
    hi = sub["reasons_hi"] if "reasons_hi" in sub else en
    cols["reason"] = np.array([ridx(a, b) for a, b in zip(en, hi)], dtype=int)
    for c, scale in [("fc_rain", 10), ("obs_rain", 10), ("rain_lo", 10), ("rain_med", 10), ("rain_hi", 10)]:
        if c in sub:
            cols[c] = np.where(np.isfinite(sub[c]), np.round(sub[c] * scale), -1).astype(int)
    if "fc_tmax_bc" in sub:
        cols["fc_tmax"] = np.where(np.isfinite(sub["fc_tmax_bc"]), np.round((sub["fc_tmax_bc"] - 273.15) * 10), -9999).astype(int)
    if "obs_heat" in sub:
        cols["obs_tmax"] = np.where(np.isfinite(sub["obs_heat"]), np.round((sub["obs_heat"] - 273.15) * 10), -9999).astype(int)
    split_of_date = sub.groupby("init")["split"].first().reindex(dates).fillna("none").tolist()

    # analogue dates (top 3) for the included dates
    analogs = {}
    ap = os.path.join(models_dir, "analog_dates.json")
    if os.path.exists(ap):
        allan = json.load(open(ap))
        keep = {str(pd.Timestamp(d).date()) for d in dates}
        analogs = {k: v for k, v in allan.items() if k.split("|")[0] in keep}
    # outcome of each analogue (did it bust in each region?) from the full predictions
    busted = pred.set_index(["init", "lead", "region"])["bust"]
    analog_outcome = {}
    for k, v in list(analogs.items()):
        L = int(k.split("|")[1])
        for d in v:
            key = f"{d}|{L}"
            if key in analog_outcome:
                continue
            analog_outcome[key] = [int(busted.get((pd.Timestamp(d), L, r), -1)) if pd.notna(busted.get((pd.Timestamp(d), L, r), np.nan)) else -1
                                   for r in regions]

    # event replays from the full predictions (all years)
    events = []
    for name, region, d0, d1, typ in EVENTS:
        pc = "p_bust" if typ == "any" or f"p_bust_{typ}" not in pred else f"p_bust_{typ}"
        ac = "bust" if typ == "any" or f"bust_{typ}" not in pred else f"bust_{typ}"
        s = pred[(pred.region == region) & (pred.valid_date >= d0) & (pred.valid_date <= d1)]
        if s.empty:
            continue
        g = s.groupby("lead").agg(p=(pc, "max"), a=(ac, "max"))
        first_init = {int(L): str((pd.Timestamp(d0) - pd.Timedelta(days=int(L) - 1)).date()) for L in leads}
        sysk = [SYSTEM_LABELS[x] for x in SYSTEMS if f"sys_{x}" in s and s[f"sys_{x}"].max() == 1]
        events.append({"name": name, "region": region, "start": d0, "end": d1, "type": typ,
                       "split": s["split"].iloc[0], "p": [int(round(100 * g.p.get(L, np.nan))) if pd.notna(g.p.get(L, np.nan)) else None for L in leads],
                       "actual": [int(g.a.get(L, 0)) if pd.notna(g.a.get(L, np.nan)) else None for L in leads],
                       "init_for_lead": first_init, "systems": sysk,
                       "obs_rain_max": round(float(s["obs_rain"].max()), 1) if "obs_rain" in s else None})

    def csv(stem):
        t = read_table(models_dir, stem)
        return None if t is None else json.loads(t.to_json(orient="records"))

    auc = read_table(models_dir, "auc_by_lead")
    if unet_path is None:
        cand = (glob.glob(os.path.join(models_dir, "..", "bustradar_unet", "unet_probs.nc"))
                + glob.glob("/kaggle/working/bustradar_unet/unet_probs.nc")
                + glob.glob(os.path.join(HERE, "..", "data", "bustradar_unet", "unet_probs.nc")))
        unet_path = cand[0] if cand else None
    unet = read_unet(unet_path, dates, leads, land) if unet_path else None
    info = {}
    if os.path.exists(os.path.join(models_dir, "run_info.json")):
        info = json.load(open(os.path.join(models_dir, "run_info.json")))
    live_src = None
    for c in glob.glob(os.path.join(models_dir, "..", "bustradar_data", "live_info.json")) + glob.glob("/kaggle/working/bustradar_data/live_info.json") + glob.glob("/kaggle/input/**/live_info.json", recursive=True):
        live_src = json.load(open(c)).get("source"); break
    rr = read_table(models_dir, "rain_range_coverage")
    bundle = {
        "meta": {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "regions": regions, "leads": leads,
                 "types": types, "type_labels": TYPE_LABELS, "systems": SYSTEMS, "system_labels": SYSTEM_LABELS,
                 "regions_hi": [REGION_HI.get(r, r) for r in regions], "type_labels_hi": TYPE_LABELS_HI,
                 "system_labels_hi": SYSTEM_LABELS_HI, "alert_threshold": info.get("alert_threshold"),
                 "live_runs": [d for d in info.get("live_runs", []) if d in {str(pd.Timestamp(x).date()) for x in dates}],
                 "live_source": live_src or "ECMWF open data (IFS)",
                 "years": years, "n_rows": int(len(sub))},
        "grid": {"lat": lat, "lon": lon, "region_id": rid, "land": land},
        "dates": [str(pd.Timestamp(d).date()) for d in dates], "date_split": split_of_date,
        "cols": {k: v.tolist() for k, v in cols.items()}, "reasons": reasons_list, "reasons_hi": reasons_hi,
        "states": read_states(rid, land),
        "rain_range_coverage": None if rr is None else json.loads(rr.to_json(orient="records")),
        "analogs": analogs, "analog_outcome": analog_outcome, "events": events,
        "metrics": csv("metrics"), "systems_table": csv("busts_by_system"),
        "auc_by_lead": None if auc is None else json.loads(auc.to_json(orient="records")),
        "unet": unet,
    }
    return bundle


def write(bundle, out):
    os.makedirs(out, exist_ok=True)
    js = json.dumps(bundle, separators=(",", ":"))
    open(os.path.join(out, "bundle.json"), "w").write(js)
    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__BUNDLE__*/null", js.replace("</", "<\\/"))
    open(os.path.join(out, "bustradar_dashboard.html"), "w", encoding="utf-8").write(html)
    print(f"wrote {out}/bundle.json ({len(js) / 1e6:.1f} MB) and {out}/bustradar_dashboard.html")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None, help="folder with predictions.parquet (notebook-02 output)")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--unet", default=None, help="unet_probs.nc from notebook 04 (optional)")
    a = ap.parse_args()
    models = a.models or next((os.path.dirname(p) for p in
                               glob.glob("/kaggle/working/bustradar_models/predictions.*")
                               + glob.glob(os.path.join(HERE, "..", "data", "bustradar_models", "predictions.*"))
                               + glob.glob("./**/bustradar_models/predictions.*", recursive=True)), None)
    if not models:
        raise SystemExit("Could not find bustradar_models. Pass --models path/to/bustradar_models")
    write(build(models, unet_path=a.unet), a.out)
