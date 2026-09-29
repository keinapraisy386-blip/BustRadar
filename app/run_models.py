"""Run notebook 02 as a plain script (used by the daily GitHub Actions job).

    python app/run_models.py --mode infer                 # predict with the saved models (live runs)
    python app/run_models.py --mode train [--no-tune]     # full training
Data is read from data/bustradar_data and models are written to / read from data/bustradar_models.
"""
import argparse, os, sys
import matplotlib
matplotlib.use("Agg")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="infer", choices=["infer", "train"])
    ap.add_argument("--no-tune", action="store_true")
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "bustradar_data"))
    ap.add_argument("--models", default=os.path.join(ROOT, "data", "bustradar_models"))
    a = ap.parse_args()
    nb = os.path.join(ROOT, "notebooks", "02_models.py")
    g = {"__name__": "__main__", "MODE": a.mode, "TUNE": not a.no_tune,
         "DATA": os.path.abspath(a.data), "OUT2": os.path.abspath(a.models)}
    if a.mode == "infer":
        g["MODELS_FROM"] = os.path.abspath(a.models)
    exec(compile(open(nb, encoding="utf-8").read(), nb, "exec"), g)
