"""BustRadar automatic alerts. Standard library only.

Print the bulletin for a model run (state-wise, English + Hindi by default):
    python app/alerts.py --date 2021-05-13 --min-p 50 --by state --lang both

Also send it to Telegram (create a bot with @BotFather, get your chat id from @userinfobot):
    python app/alerts.py --date 2021-05-13 --telegram-token 123:ABC --telegram-chat 987654

Also write it to a file (e.g. for an email job or a web page):
    python app/alerts.py --date 2021-05-13 --out alerts/2021-05-13.txt

In operations this runs after every forecast cycle, e.g. with cron (06:30 UTC daily):
    30 6 * * *  cd /path/to/bustradar && python app/alerts.py --latest --telegram-token ... --telegram-chat ...
"""
import argparse, json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import Store, bulletin

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=os.path.join(HERE, "dist", "bundle.json"))
    ap.add_argument("--date"); ap.add_argument("--latest", action="store_true")
    ap.add_argument("--min-p", type=float, default=None, help="alert threshold in %% (default: tuned value from notebook 02, else 50)")
    ap.add_argument("--by", default="state", choices=["state", "region"])
    ap.add_argument("--lang", default="both", choices=["en", "hi", "both"])
    ap.add_argument("--telegram-token"); ap.add_argument("--telegram-chat")
    ap.add_argument("--out")
    a = ap.parse_args()
    store = Store(a.bundle)
    date = store.B["dates"][-1] if (a.latest or not a.date) else a.date
    if date not in store.date_idx:
        sys.exit(f"No model run for {date}. First: {store.B['dates'][0]}, last: {store.B['dates'][-1]}")
    mp = a.min_p if a.min_p is not None else round(100 * (store.B["meta"].get("alert_threshold") or 0.5))
    langs = ["en", "hi"] if a.lang == "both" else [a.lang]
    text = "\n\n".join(bulletin(store, date, mp, a.by, l) for l in langs)
    print(text)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(text); print(f"\nSaved to {a.out}")
    if a.telegram_token and a.telegram_chat:
        data = urllib.parse.urlencode({"chat_id": a.telegram_chat, "text": text}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{a.telegram_token}/sendMessage", data=data, timeout=30) as r:
                ok = json.loads(r.read()).get("ok")
            print("\nTelegram:", "sent" if ok else "failed")
        except Exception as e:
            print("\nTelegram failed:", e)
