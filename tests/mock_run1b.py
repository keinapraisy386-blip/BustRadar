"""Offline test of notebook 01b (run mock_run.py first, same MOCK_YEARS)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_data import *
import matplotlib; matplotlib.use("Agg")
NB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "notebooks", "01b_extra_data.py")
src = open(NB).read()
cells = re.split(r"^# %%.*$", src, flags=re.M); headers = re.findall(r"^# %%.*$", src, flags=re.M)
g = {"MOCK": True, "OUT": os.path.abspath("mock_out"), "make_mock_wb2": make_mock_wb2, "era5_coarse_mock": era5_coarse_mock,
     "make_mock_imd_tmax": make_mock_imd_tmax, "__name__": "__main__"}
for h, c in zip(headers, cells[1:]):
    if "markdown" in h: continue
    title = c.strip().splitlines()[0]; print("\n=====", title)
    exec(compile(c, title, "exec"), g)
