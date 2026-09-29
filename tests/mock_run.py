"""Offline end-to-end test of notebook 01 with synthetic data. Set MOCK_YEARS=2016,2020,2021 for notebook-02 tests."""
import os, sys, re, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_data import *
NB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "notebooks", "01_data_pipeline.py")
# ---- run notebook cells --------------------------------------------------------------
src = open(NB).read()
cells = re.split(r"^# %%.*$", src, flags=re.M)
headers = re.findall(r"^# %%.*$", src, flags=re.M)
g = {"MOCK": True, "make_mock_wb2": make_mock_wb2, "make_mock_imd": make_mock_imd, "__name__": "__main__"}
import matplotlib; matplotlib.use("Agg")
out = os.path.abspath("mock_out"); shutil.rmtree(out, ignore_errors=True)
for h, c in zip(headers, cells[1:]):
    if "markdown" in h: continue
    title = c.strip().splitlines()[0]
    print("\n=====", title)
    exec(compile(c, title, "exec"), g)
    if "2. Config" in title:
        g.update(YEARS=MOCK_YEARS, TRAIN_YEARS=MOCK_YEARS[:-1], TEST_YEARS=MOCK_YEARS[-1:], OUT=out)
        os.makedirs(f"{out}/maps", exist_ok=True)
df = g["df"]
print("\nROWS", df.shape, "| SHIFT", g["SHIFT"])
print(df.filter(regex="^(init|lead|region|fc_rain|obs_rain|rain_rmse|jump_rain|bust)").head(12).to_string())
