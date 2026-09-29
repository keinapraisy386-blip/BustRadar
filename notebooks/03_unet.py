# %% [markdown]
# # BustRadar — U-Net: grid-level error-prone area detection
#
# Predicts, for every 1.5° grid cell over India and every lead day, the probability that the rainfall
# forecast will be badly wrong there. This is the **error-prone area map** asked for in PS 26079.
#
# * Input per forecast: rain, 500 hPa height / pressure anomalies, 850 hPa winds, moisture, Tmax, 10 m wind,
#   200 hPa wind, lagged-run spread, run-to-run jump, lead day, season, land mask (15 channels, 24×24)
# * Target: cell error above its own 90th percentile (per lead × season, training years), at least 10 mm/day
# * Model: small U-Net, **3 copies with different seeds** (deep ensemble). The spread between them tells you
#   how sure the network itself is.
# * **Runs on CPU** in the same Kaggle session after notebook 02 (~15 min per model; set `N_MODELS = 1` to go faster).
#   With a GPU it takes a few minutes.

# %%
# ---- 1. Setup and data -------------------------------------------------------------------------
import os, glob, json, time, warnings
import numpy as np, pandas as pd, xarray as xr
def _load(path):
    with xr.open_dataset(path) as d:
        return d.load()
warnings.filterwarnings("ignore")

def find(sub):
    c = (glob.glob(f"/kaggle/working/bustradar_data/{sub}") + glob.glob(f"/kaggle/input/**/{sub}", recursive=True)
         + glob.glob(f"./data/bustradar_data/{sub}") + glob.glob(f"../data/bustradar_data/{sub}") + glob.glob(f"./**/{sub}", recursive=True))
    return os.path.dirname(c[0]) if c else None
DATA = globals().get("DATA") or find("grid_meta.nc")
OUT = globals().get("OUT4") or ("/kaggle/working/bustradar_unet" if os.path.exists("/kaggle") else "./bustradar_unet")
os.makedirs(OUT, exist_ok=True)
FIT_YEARS, VAL_YEARS, TEST_YEARS = [2016, 2017, 2018, 2019], [2020], [2021, 2022]
split_fn = globals().get("SPLIT_FN")
N_MODELS, EPOCHS, BATCH, SEED = globals().get("N_MODELS", 3), globals().get("EPOCHS", 25), 64, 42
FLOOR_MM, BUST_Q = 10.0, 0.90

with xr.open_dataset(os.path.join(DATA, "grid_meta.nc")) as _m:
    meta = _m.load()
TLAT, TLON, LAND = meta.lat.values, meta.lon.values, meta.land.values.astype(bool)
def load(prefix, dim):
    f = sorted(glob.glob(os.path.join(DATA, "maps", f"{prefix}_*.nc")))
    if not f: return None
    d = xr.concat([_load(x) for x in f], dim=dim).sortby(dim)
    return d.isel({dim: ~pd.Index(d[dim].values).duplicated()})
fc, fcx, obs = load("fc", "init"), load("fcx", "init"), load("obs", "date")
if fcx is not None: fcx = fcx.reindex(init=fc.init)
INITS = pd.DatetimeIndex(fc.init.values); NI, NL, NY, NX = len(INITS), fc.sizes["lead"], len(TLAT), len(TLON)
LEADS = fc.lead.values
SPLIT = (split_fn(pd.Series(INITS)) if split_fn else
         np.select([INITS.year.isin(FIT_YEARS), INITS.year.isin(VAL_YEARS), INITS.year.isin(TEST_YEARS)], ["fit", "val", "test"], "none"))
SPLIT = np.asarray(SPLIT); fit_i = SPLIT == "fit"
print(f"{NI} forecasts x {NL} leads on {NY}x{NX} grid | fit {fit_i.sum()}, val {(SPLIT == 'val').sum()}, test {(SPLIT == 'test').sum()}")

# %%
# ---- 2. Inputs (channels) and targets ------------------------------------------------------------
def arr(ds, v):
    return None if ds is None or v not in ds else ds[v].transpose("init", "lead", "lat", "lon").values.astype("float32")
MONTH = INITS.month.values
def anom(a):
    c = np.zeros((13,) + a.shape[2:], "float32")
    for m in range(1, 13):
        s = fit_i & (MONTH == m)
        if s.any(): c[m] = np.nanmean(a[s], axis=(0, 1))
    return a - c[MONTH][:, None]
idx = pd.Index(INITS)
def shifted(a, k):             # value for the same valid day from the run k days earlier
    out = np.full_like(a, np.nan); pp = idx.get_indexer(INITS - pd.Timedelta(days=k)); ok = pp >= 0
    out[ok, :NL - k] = a[pp[ok], k:]; return out

rain = np.log1p(np.clip(arr(fc, "rain"), 0, None))
lag = np.stack([rain] + [shifted(rain, k) for k in (1, 2, 3)])
cnt = np.isfinite(lag).sum(0); lag_sd = np.nanstd(lag, 0); lag_sd[cnt < 2] = np.nan
channels = {"rain": rain, "lag_spread": lag_sd, "jump": rain - shifted(rain, 1)}
for v, how in [("z500", "anom"), ("mslp", "anom"), ("u850", None), ("v850", None), ("q700", "anom")]:
    a = arr(fc, v)
    if a is not None: channels[v] = anom(a) if how else a
for v, how in [("tmax", "anom"), ("wind10max", None), ("u200", None)]:
    a = arr(fcx, v)
    if a is not None: channels[v] = anom(a) if how else a
doy = INITS.dayofyear.values[:, None] + (LEADS - 1)[None, :]
const = lambda x: np.broadcast_to(x[:, :, None, None], (NI, NL, NY, NX)).astype("float32")
channels["lead"] = const(np.broadcast_to(LEADS[None, :] / 10.0, (NI, NL)))
channels["doy_sin"], channels["doy_cos"] = const(np.sin(2 * np.pi * doy / 365.25)), const(np.cos(2 * np.pi * doy / 365.25))
channels["land"] = np.broadcast_to(LAND[None, None].astype("float32"), (NI, NL, NY, NX))
CH = list(channels)
X = np.stack([channels[c] for c in CH], axis=2).astype("float32")          # (init, lead, C, y, x)
mu = np.nanmean(X[fit_i], axis=(0, 1, 3, 4), keepdims=True); sd = np.nanstd(X[fit_i], axis=(0, 1, 3, 4), keepdims=True) + 1e-6
for k, c in enumerate(CH):
    if c in ("land",): mu[..., k, :, :], sd[..., k, :, :] = 0, 1
X = np.nan_to_num((X - mu) / sd).astype("float32")
del channels, lag

# target: cell error above its own 90th percentile (lead x season, fit+val years) and >= FLOOR_MM
valid = INITS.values[:, None] + (LEADS - 1)[None, :] * np.timedelta64(1, "D")
o = obs["rain"].transpose("date", "lat", "lon"); pos = pd.Index(pd.DatetimeIndex(o.date.values)).get_indexer(valid.ravel())
ov = np.full((valid.size, NY, NX), np.nan, "float32"); ov[pos >= 0] = o.values[pos[pos >= 0]]
err = np.abs(arr(fc, "rain") - ov.reshape(NI, NL, NY, NX))
SEASON = np.select([np.isin(MONTH, [12, 1, 2]), np.isin(MONTH, [3, 4, 5]), np.isin(MONTH, [6, 7, 8, 9])], [0, 1, 2], 3)
trn = np.isin(SPLIT, ["fit", "val"])
thr = np.full((4, NL, NY, NX), np.inf, "float32")
for s in range(4):
    sel = trn & (SEASON == s)
    if sel.any(): thr[s] = np.maximum(np.nanpercentile(err[sel], 100 * BUST_Q, axis=0), FLOOR_MM)
Y = (err > thr[SEASON]).astype("float32")
M = (np.isfinite(err) & LAND[None, None]).astype("float32")               # where the label is defined
Y[M == 0] = 0
print(f"Channels ({len(CH)}): {CH}\nCell bust rate (fit): {Y[fit_i][M[fit_i] > 0].mean():.3f}")

# %%
# ---- 3. Model (PyTorch) ------------------------------------------------------------------------------
import torch, torch.nn as nn, torch.nn.functional as F
DEV = "cuda" if torch.cuda.is_available() else "cpu"
torch.set_num_threads(max(1, os.cpu_count() or 1))
print("Device:", DEV)

class Block(nn.Module):
    def __init__(self, i, o, drop=0.0):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.GELU(),
                                 nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.GELU(), nn.Dropout2d(drop))
    def forward(self, x): return self.net(x)

class UNet(nn.Module):
    """24x24 -> 12x12 -> 6x6 and back, with skip connections."""
    def __init__(self, cin, c=32):
        super().__init__()
        self.e1, self.e2, self.b = Block(cin, c), Block(c, 2 * c), Block(2 * c, 4 * c, drop=0.15)
        self.u2, self.d2 = nn.ConvTranspose2d(4 * c, 2 * c, 2, stride=2), Block(4 * c, 2 * c)
        self.u1, self.d1 = nn.ConvTranspose2d(2 * c, c, 2, stride=2), Block(2 * c, c)
        self.out = nn.Conv2d(c, 1, 1)
    def forward(self, x):
        e1 = self.e1(x); e2 = self.e2(F.max_pool2d(e1, 2)); b = self.b(F.max_pool2d(e2, 2))
        d2 = self.d2(torch.cat([self.u2(b), e2], 1)); d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
        return self.out(d1)[:, 0]

def flat(sel):                                   # (init, lead, ...) -> samples
    return X[sel].reshape(-1, len(CH), NY, NX), Y[sel].reshape(-1, NY, NX), M[sel].reshape(-1, NY, NX)
Xf, Yf, Mf = flat(fit_i); Xv, Yv, Mv = flat(SPLIT == "val")
pos_rate = Yf[Mf > 0].mean(); POS_W = float(np.sqrt((1 - pos_rate) / max(pos_rate, 1e-6)))

def masked_bce(logit, y, m):
    l = F.binary_cross_entropy_with_logits(logit, y, pos_weight=torch.tensor(POS_W, device=logit.device), reduction="none")
    return (l * m).sum() / m.sum().clamp(min=1)

@torch.no_grad()
def predict(model, Xs, bs=512):
    model.eval(); out = []
    for i in range(0, len(Xs), bs):
        out.append(torch.sigmoid(model(torch.from_numpy(Xs[i:i + bs]).to(DEV))).float().cpu().numpy())
    return np.concatenate(out)

def train_one(seed):
    torch.manual_seed(seed); np.random.seed(seed)
    model = UNet(len(CH)).to(DEV)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=EPOCHS * int(np.ceil(len(Xf) / BATCH)))
    best, best_state, bad = np.inf, None, 0
    for ep in range(EPOCHS):
        model.train(); perm = np.random.permutation(len(Xf)); tl = 0.0; t0 = time.time()
        for i in range(0, len(perm), BATCH):
            b = perm[i:i + BATCH]
            xb, yb, mb = (torch.from_numpy(a[b]).to(DEV) for a in (Xf, Yf, Mf))
            loss = masked_bce(model(xb), yb, mb)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step(); tl += loss.item() * len(b)
        model.eval()
        with torch.no_grad():
            vl, n = 0.0, 0
            for i in range(0, len(Xv), 512):
                xb, yb, mb = (torch.from_numpy(a[i:i + 512]).to(DEV) for a in (Xv, Yv, Mv))
                vl += masked_bce(model(xb), yb, mb).item() * len(xb); n += len(xb)
        vl /= max(n, 1)
        print(f"  seed {seed} epoch {ep + 1:2d}  train {tl / len(Xf):.4f}  val {vl:.4f}  ({time.time() - t0:.0f}s)", flush=True)
        if vl < best - 1e-4:
            best, bad = vl, 0; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= 5: break
    model.load_state_dict(best_state)
    return model

# %%
# ---- 4. Train the deep ensemble -------------------------------------------------------------------------
models = []
for k in range(N_MODELS):
    t0 = time.time(); models.append(train_one(SEED + k))
    torch.save(models[-1].state_dict(), f"{OUT}/unet_seed{SEED + k}.pt")
    print(f"model {k + 1}/{N_MODELS} done in {(time.time() - t0) / 60:.1f} min")
eval_sel = np.isin(SPLIT, ["val", "test"])
Xe = X[eval_sel].reshape(-1, len(CH), NY, NX)
P_all = np.stack([predict(m, Xe) for m in models])                         # (models, samples, y, x)
P_MEAN = P_all.mean(0).reshape(eval_sel.sum(), NL, NY, NX)
P_SPREAD = P_all.std(0).reshape(eval_sel.sum(), NL, NY, NX)

# %%
# ---- 4b. Calibrate: make "30%" mean 30% (training up-weights busts, which inflates raw probabilities) ----
from sklearn.isotonic import IsotonicRegression
_va = SPLIT[eval_sel] == "val"
_Yv, _Mv = Y[eval_sel][_va], M[eval_sel][_va] > 0
P_RAW = P_MEAN.copy()
for li in range(NL):
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(P_RAW[_va][:, li][_Mv[:, li]], _Yv[:, li][_Mv[:, li]])
    P_MEAN[:, li] = iso.predict(P_RAW[:, li].ravel()).reshape(P_RAW[:, li].shape)
print("Calibrated per lead day on the validation year (2020).")

# %%
# ---- 5. Evaluate on the test years ------------------------------------------------------------------------
from sklearn.metrics import roc_auc_score, brier_score_loss
E_INITS = INITS[eval_sel]; E_SPLIT = SPLIT[eval_sel]
te = E_SPLIT == "test"
y = Y[eval_sel][te]; m = M[eval_sel][te] > 0; p = P_MEAN[te]
clim = np.zeros((4, NL, NY, NX), "float32")                               # baseline: cell bust rate (train)
for s in range(4):
    sel = trn & (SEASON == s)
    if sel.any(): clim[s] = np.nanmean(np.where(M[sel] > 0, Y[sel], np.nan), axis=0)
pc = np.nan_to_num(clim[SEASON[eval_sel][te]])
spread_raw = X[eval_sel][te][:, :, CH.index("lag_spread")]
res = {"AUC_unet": roc_auc_score(y[m], p[m]), "AUC_climatology": roc_auc_score(y[m], pc[m]),
       "AUC_lagged_spread_only": roc_auc_score(y[m], spread_raw[m]),
       "Brier_skill_vs_clim": 1 - brier_score_loss(y[m], p[m]) / brier_score_loss(y[m], pc[m]),
       "cell_bust_rate": float(y[m].mean()), "n_cells": int(m.sum())}
by_lead = [roc_auc_score(y[:, i][m[:, i]], p[:, i][m[:, i]]) if y[:, i][m[:, i]].std() > 0 else np.nan for i in range(NL)]
res["AUC_by_lead"] = [round(float(v), 3) for v in by_lead]
print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items()}, indent=1))
json.dump(res, open(f"{OUT}/unet_metrics.json", "w"), indent=1)

# %%
# ---- 6. Picture: predicted error-prone areas vs what actually happened ----------------------------------------
import matplotlib.pyplot as plt
want = pd.Timestamp("2021-05-13")                          # Cyclone Tauktae, Day 3 forecast
ti = np.where(E_INITS == want)[0]
if len(ti): qi, li = int(ti[0]), 2
else:
    flatp = np.where(te[:, None], P_MEAN.mean((2, 3)), -1); qi, li = np.unravel_index(np.argmax(flatp), flatp.shape)
ext = [TLON[0] - .75, TLON[-1] + .75, TLAT[0] - .75, TLAT[-1] + .75]
fig, ax = plt.subplots(1, 4, figsize=(17, 4.3))
land_bg = np.where(LAND, 1.0, np.nan)
panels = [(arr(fc, "rain")[eval_sel][qi, li], "Forecast rain (mm/day)", "Blues", None),
          (np.where(LAND, P_MEAN[qi, li], np.nan), "U-Net P(bust)", "YlOrRd", (0, 1)),
          (np.where(LAND, P_SPREAD[qi, li], np.nan), "Ensemble disagreement", "Purples", None),
          (np.where(M[eval_sel][qi, li] > 0, Y[eval_sel][qi, li], np.nan), "Actual bust cells", "Reds", (0, 1))]
for a, (img, title, cmap, lim) in zip(ax, panels):
    a.imshow(land_bg, origin="lower", extent=ext, cmap="Greys", vmin=0, vmax=4)
    im = a.imshow(img, origin="lower", extent=ext, cmap=cmap, vmin=None if lim is None else lim[0], vmax=None if lim is None else lim[1])
    a.set_title(title); a.set_xlabel("°E"); plt.colorbar(im, ax=a, fraction=0.046)
ax[0].set_ylabel("°N")
fig.suptitle(f"Run {E_INITS[qi].date()} · Day {LEADS[li]}  (valid {(E_INITS[qi] + pd.Timedelta(days=int(LEADS[li]) - 1)).date()})")
plt.tight_layout(); plt.savefig(f"{OUT}/fig_unet_example.png"); plt.show()

# %%
# ---- 7. Save for the dashboard ---------------------------------------------------------------------------------
ds = xr.Dataset({"p": (("init", "lead", "lat", "lon"), np.round(100 * P_MEAN).astype("int16")),
                 "spread": (("init", "lead", "lat", "lon"), np.round(100 * P_SPREAD).astype("int16"))},
                coords={"init": E_INITS, "lead": LEADS, "lat": TLAT, "lon": TLON},
                attrs={"channels": json.dumps(CH), "split": json.dumps(dict(zip(map(str, E_INITS.date), E_SPLIT)))})
ds.to_netcdf(f"{OUT}/unet_probs.nc")
import shutil
print("Saved", f"{OUT}/unet_probs.nc", "| zip:", shutil.make_archive(OUT, "zip", OUT))
