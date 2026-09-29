"""BustRadar API + dashboard server. Standard library only: no pip install needed.

    python app/server.py                       # uses app/dist/bundle.json
    python app/server.py --bundle path/to/bundle.json --port 8000

Open http://localhost:8000 for the dashboard. JSON endpoints:
    /api/dates
    /api/forecast?date=YYYY-MM-DD[&lead=N]
    /api/region?date=YYYY-MM-DD&region=West%20Coast
    /api/states?date=YYYY-MM-DD[&lead=N]
    /api/alerts?date=YYYY-MM-DD&min_p=50[&by=state|region][&lang=en|hi]
    /api/report?date=YYYY-MM-DD[&min_p=50]      (yesterday's report card as seen on that date)
    /api/events      /api/metrics      /api/bundle
"""
import argparse, json, os, datetime as dt
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))


class Store:
    def __init__(self, path):
        self.B = json.load(open(path))
        m = self.B["meta"]
        self.regions, self.leads, self.types = m["regions"], m["leads"], m["types"]
        self.R, self.NL = len(self.regions), len(self.leads)
        self.date_idx = {d: i for i, d in enumerate(self.B["dates"])}
        self.C = self.B["cols"]
        self.states = [s for s in ((self.B.get("states") or {}).get("states") or []) if s.get("scored")]
        self.reasons_hi = self.B.get("reasons_hi") or self.B["reasons"]

    def val(self, col, d, li, r):
        c = self.C.get(col); return c[self.ix(d, li, r)] if c else -1

    def rain_range(self, d, li, r):
        lo, md, hi = (self.val(c, d, li, r) for c in ("rain_lo", "rain_med", "rain_hi"))
        return None if lo < 0 or hi < 0 else {"low": lo / 10, "median": md / 10, "high": hi / 10}

    def ix(self, d, li, r):
        return (d * self.NL + li) * self.R + r

    def cell(self, date, li, r, lang="en"):
        d = self.date_idx[date]; i = self.ix(d, li, r); C = self.C
        p = C["p"][i]
        if p < 0:
            return None
        L = self.leads[li]
        valid = (dt.date.fromisoformat(date) + dt.timedelta(days=L - 1)).isoformat()
        sysm = C["sys"][i]
        sl = self.B["meta"].get("system_labels_hi" if lang == "hi" else "system_labels") or self.B["meta"]["system_labels"]
        systems = [sl[s] for k, s in enumerate(self.B["meta"]["systems"]) if (sysm >> k) & 1]
        rk = C["reason"][i]
        by_type = {t: C[f"p_{t}"][i] / 100 for t in self.types if f"p_{t}" in C}
        rlist = self.reasons_hi if lang == "hi" else self.B["reasons"]
        return {"region": self.regions[r], "lead": L, "valid_date": valid, "confidence": 100 - p, "p_bust": p / 100,
                "band": "high" if 100 - p >= 70 else "medium" if 100 - p >= 50 else "low",
                "p_by_type": by_type, "main_risk": max(by_type, key=by_type.get) if by_type else None,
                "systems": systems, "reasons": rlist[rk].split(" | ") if rk >= 0 else [],
                "rain_range_mm": self.rain_range(d, li, r)}

    def forecast(self, date, lead=None, lang="en"):
        lis = [self.leads.index(int(lead))] if lead else range(self.NL)
        return [c for li in lis for r in range(self.R) if (c := self.cell(date, li, r, lang))]

    def state_cell(self, date, li, st, lang="en"):
        """State value = area-weighted mix of the forecast regions the state lies in (same as the dashboard)."""
        d = self.date_idx[date]
        def mix(col):
            v = [(self.val(col, d, li, r), w) for r, w in st["regions"]]
            return None if not v or any(x < 0 for x, _ in v) else round(sum(x * w for x, w in v))
        p = mix("p")
        if p is None:
            return None
        by_type = {t: (mix(f"p_{t}") or 0) / 100 for t in self.types}
        base = self.cell(date, li, st["regions"][0][0], lang)          # reasons + rain range from the main region
        return {"state": st["name"], "state_hi": st["name_hi"], "lead": base["lead"], "valid_date": base["valid_date"],
                "confidence": 100 - p, "p_bust": p / 100, "band": "high" if 100 - p >= 70 else "medium" if 100 - p >= 50 else "low",
                "p_by_type": by_type, "main_risk": max(by_type, key=by_type.get) if by_type else None,
                "regions": {self.regions[r]: w for r, w in st["regions"]},
                "systems": base["systems"], "reasons": base["reasons"], "rain_range_mm": base["rain_range_mm"]}

    def state_forecast(self, date, lead=None, lang="en"):
        lis = [self.leads.index(int(lead))] if lead else range(self.NL)
        return [c for li in lis for st in self.states if (c := self.state_cell(date, li, st, lang))]

    def alerts(self, date, min_p=50, by="region", lang="en"):
        rows = self.state_forecast(date, lang=lang) if by == "state" and self.states else self.forecast(date, lang=lang)
        return sorted([c for c in rows if c["p_bust"] * 100 >= min_p], key=lambda c: (-c["p_bust"], c["lead"]))

    def report(self, date, min_p=50):
        """Yesterday's report card: every forecast valid on (date - 1), issued 1-10 days earlier."""
        V = dt.date.fromisoformat(date) - dt.timedelta(days=1)
        tally, rows = {"caught": 0, "false_alarm": 0, "missed": 0, "correct_quiet": 0, "not_verified": 0}, []
        for li, L in enumerate(self.leads):
            issued = (V - dt.timedelta(days=L - 1)).isoformat()
            for r, reg in enumerate(self.regions):
                o = "not_verified"
                if issued in self.date_idx:
                    d = self.date_idx[issued]; a, p = self.val("actual", d, li, r), self.val("p", d, li, r)
                    if a >= 0 and p >= 0:
                        o = ("caught" if a > 0 else "false_alarm") if p >= min_p else ("missed" if a > 0 else "correct_quiet")
                    rows.append({"region": reg, "lead": L, "issued": issued, "p_bust": p / 100 if p >= 0 else None, "outcome": o})
                tally[o] += 1
        return {"valid_date": V.isoformat(), "min_p": min_p, "summary": tally, "forecasts": rows}


def _mm(v):
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}"


def bulletin(store, date, min_p=50, by="region", lang="en"):
    by = by if by == "state" and store.states else "region"
    A = store.alerts(date, min_p, by, lang)
    hi, m = lang == "hi", store.B["meta"]
    tl = m.get("type_labels_hi") if hi else m["type_labels"]
    reg_hi = dict(zip(m["regions"], m.get("regions_hi") or m["regions"]))
    live = date in set(m.get("live_runs") or [])
    if hi:
        lines = [f"बस्टरडार पूर्वानुमान-विश्वसनीयता बुलेटिन ({'राज्यवार' if by == 'state' else 'क्षेत्रवार'})",
                 f"मॉडल रन: {date}, 00 UTC   चेतावनी सीमा: बस्ट की संभावना ≥ {min_p:g}%"]
    else:
        lines = [f"BUSTRADAR FORECAST-CONFIDENCE BULLETIN ({'STATE-WISE' if by == 'state' else 'REGION-WISE'})",
                 f"Model run: {date} 00 UTC   Alert threshold: P(bust) >= {min_p:g}%"]
    if live:
        lines.append(("लाइव रन: " if hi else "Live run: ") + m.get("live_source", "ECMWF open data"))
    lines.append("")
    if not A:
        lines.append("किसी भी क्षेत्र में कम विश्वसनीयता नहीं। मॉडल मार्गदर्शन का सामान्य रूप से उपयोग करें।" if hi
                     else "No low-confidence areas. Model guidance can be used as usual.")
    key = "state" if by == "state" else "region"
    groups = {}
    for c in A:
        groups.setdefault(c[key], []).append(c)
    for name, g in groups.items():
        g = sorted(g, key=lambda c: c["lead"]); top = max(g, key=lambda c: c["p_bust"])
        days, pm, typ = ", ".join(str(c["lead"]) for c in g), round(100 * top["p_bust"]), tl.get(top["main_risk"], top["main_risk"])
        shown = (top.get("state_hi") if by == "state" else reg_hi.get(name, name)) if hi else name.upper()
        lines.append(f"{shown}: दिन {days} के लिए कम विश्वसनीयता (अधिकतम {pm}%, मुख्यतः {typ})" if hi
                     else f"{shown}: low confidence on Day {days} (max {pm}%, mainly {typ if top['main_risk'] == 'z500' else typ.lower()})")
        why = (top["systems"] + top["reasons"])[:3]
        if why:
            lines.append(("  कारण: " if hi else "  Why: ") + "; ".join(why))
        rr = top.get("rain_range_mm")
        if rr and (top["main_risk"] == "rain" or rr["high"] >= 20):
            lines.append(f"  वर्षा (दिन {top['lead']}): {_mm(rr['low'])}–{_mm(rr['high'])} मिमी/दिन अपेक्षित (90% सीमा)" if hi
                         else f"  Rain (Day {top['lead']}): expect {_mm(rr['low'])}-{_mm(rr['high'])} mm/day (90% range)")
    lines += ["", "विश्वसनीयता सूचकांक = 100 − बस्ट की संभावना। बस्टरडार द्वारा स्वतः तैयार।" if hi
              else "Confidence Index = 100 - P(bust). Generated automatically by BustRadar."]
    return "\n".join(lines)


def make_handler(store, html_path):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, indent=1, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self._send(200, open(html_path, "rb").read(), "text/html")
                if u.path == "/api/bundle":
                    return self._send(200, store.B)
                if u.path == "/api/dates":
                    return self._send(200, {"dates": store.B["dates"], "splits": store.B["date_split"]})
                if u.path in ("/api/forecast", "/api/region", "/api/alerts", "/api/states", "/api/report"):
                    date = q.get("date") or store.B["dates"][-1]
                    if date not in store.date_idx:
                        return self._send(404, {"error": f"No model run for {date}. See /api/dates."})
                    lang = q.get("lang", "en")
                    if u.path == "/api/forecast":
                        return self._send(200, {"date": date, "forecasts": store.forecast(date, q.get("lead"), lang)})
                    if u.path == "/api/states":
                        return self._send(200, {"date": date, "forecasts": store.state_forecast(date, q.get("lead"), lang)})
                    if u.path == "/api/report":
                        return self._send(200, store.report(date, float(q.get("min_p", 50))))
                    if u.path == "/api/region":
                        reg = q.get("region", "")
                        if reg not in store.regions:
                            return self._send(400, {"error": f"Unknown region. Use one of: {store.regions}"})
                        r = store.regions.index(reg)
                        return self._send(200, {"date": date, "region": reg,
                                                "forecasts": [c for li in range(store.NL) if (c := store.cell(date, li, r, lang))]})
                    mp = float(q.get("min_p", 50)); by = q.get("by", "region")
                    return self._send(200, {"date": date, "min_p": mp, "by": by, "alerts": store.alerts(date, mp, by, lang),
                                            "bulletin": bulletin(store, date, mp, by, lang)})
                if u.path == "/api/events":
                    return self._send(200, store.B.get("events", []))
                if u.path == "/api/metrics":
                    return self._send(200, {"metrics": store.B.get("metrics"), "auc_by_lead": store.B.get("auc_by_lead"),
                                            "systems": store.B.get("systems_table")})
                return self._send(404, {"error": "Not found. Try /api/dates"})
            except Exception as e:
                return self._send(500, {"error": str(e)})

        def log_message(self, fmt, *args):
            print("  ", self.address_string(), fmt % args)
    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=os.path.join(HERE, "dist", "bundle.json"))
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    store = Store(a.bundle)
    tpl = os.path.join(os.path.dirname(a.bundle), "dashboard_server.html")
    # a copy of the template WITHOUT embedded data: the page fetches /api/bundle instead
    open(tpl, "w", encoding="utf-8").write(open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read())
    print(f"BustRadar running: http://localhost:{a.port}   ({len(store.B['dates'])} model runs loaded)")
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(store, tpl)).serve_forever()
