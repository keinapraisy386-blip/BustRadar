"""Test notebook 03 without torch: runs data prep, fakes the network output, then runs evaluation + saving."""
import os, re, numpy as np
import matplotlib; matplotlib.use("Agg")
NB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "notebooks", "03_unet.py")
src = open(NB).read()
cells = re.split(r"^# %%.*$", src, flags=re.M); heads = re.findall(r"^# %%.*$", src, flags=re.M)
def split_fn(init):
    y = init.dt.year
    return np.select([y == 2016, y == 2020, y == 2021], ["fit", "val", "test"], "none")
g = {"DATA": os.path.abspath("mock_out"), "OUT4": os.path.abspath("mock_unet"), "SPLIT_FN": split_fn, "__name__": "__main__"}
for h, c in zip(heads, cells[1:]):
    if "markdown" in h: continue
    t = c.strip().splitlines()[0]
    if "3. Model" in t or "4. Train" in t:
        if "4. Train" in t:       # fake ensemble: noisy truth so the metrics are meaningful
            ev = np.isin(g["SPLIT"], ["val", "test"]); rng = np.random.default_rng(0)
            base = g["Y"][ev] * 0.6 + 0.2 * rng.random(g["Y"][ev].shape)
            g.update(eval_sel=ev, P_MEAN=base.astype("float32"), P_SPREAD=(0.05 * rng.random(base.shape)).astype("float32"))
            print("\n===== (fake network output)")
        continue
    print("\n=====", t); exec(compile(c, t, "exec"), g)
