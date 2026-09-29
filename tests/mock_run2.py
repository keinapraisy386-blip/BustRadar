"""Offline test of notebook 02 on the output of mock_run.py (run with MOCK_YEARS=2016,2020,2021)."""
import os, re, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
NB = os.path.join(os.path.dirname(__file__), "..", "notebooks", "02_models.py")
src = open(NB).read()
cells = re.split(r"^# %%.*$", src, flags=re.M); headers = re.findall(r"^# %%.*$", src, flags=re.M)
def split_fn(init):
    y = init.dt.year
    return np.select([y == 2016, y == 2020, y == 2021, y > 2022], ["fit", "val", "test", "live"], "none")
g = {"DATA": os.path.abspath(os.environ.get("MOCK_DATA", "mock_out")), "OUT2": os.path.abspath(os.environ.get("MOCK_MODELS_OUT", "mock_models")),
     "SPLIT_FN": split_fn, "__name__": "__main__", "MODE": os.environ.get("MODE", "train"),
     "TUNE": os.environ.get("TUNE", "1") == "1", "N_TRIALS": int(os.environ.get("N_TRIALS", "2"))}
if os.environ.get("MODELS_FROM"): g["MODELS_FROM"] = os.path.abspath(os.environ["MODELS_FROM"])
for h, c in zip(headers, cells[1:]):
    if "markdown" in h: continue
    title = c.strip().splitlines()[0]; print("\n=====", title)
    exec(compile(c, title, "exec"), g)
    if os.environ.get("INJECT") and "5. Anomalies" in title:        # fake weather systems to test section 10
        d = g["df"]; rs = np.random.default_rng(1)
        for k in ["sys_depression", "sys_cyclone", "sys_wd"]:
            d[k] = (rs.random(len(d)) < 0.05).astype(float)
        d.loc[d["sys_depression"] == 1, "bust_rain"] = (rs.random(int(d["sys_depression"].sum())) < 0.4).astype(int)
        d["obs_monsoon_phase"] = rs.choice(["active", "break", "normal"], len(d))
