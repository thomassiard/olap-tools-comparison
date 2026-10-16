#!/usr/bin/env python3
"""
Izvlači vremena iz dnevnika Tableau Publica (My Tableau Repository/Logs/log*.txt) i upisuje ih u results/raw.csv.

Tableau Public nema ugrađeno snimanje performansi (Performance Recording postoji samo u
Tableau Desktop/Server), ali svaki događaj zapisuje u JSON dnevnik s trajanjem ("a.elapsed", sekunde).

Postupak (po upitu): otvori list (sheet) s grafikonom za taj upit -> 6 puta Data > <izvor> > Refresh
(ili Fn+F5), s 2-3 s razmaka -> odmah zatim:

  python parse_tableau.py --query Q2            # zadnjih 6 osvježavanja, prvo se odbacuje
  python parse_tableau.py --query Q2 --dry      # samo ispiši

Metrike po osvježavanju (sve u istom vremenskom prozoru, do sljedećeg osvježavanja):
  data_ms    = trajanje "compute-model-task.compute-worksheet-data" (upit nad ekstraktom za vizualizaciju)
  render_ms  = "visual-controller.update-visual-model" umanjeno za data_ms (izgradnja i raspored prikaza)
  reload_ms  = trajanje cijele naredbe "refresh-datasource-ui" (ponovno čitanje CSV-a + upit + prikaz), informativno
"""
import argparse, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import row, write_rows  # noqa

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "My Tableau Repository", "Logs")


def latest_log(d):
    files = [f for f in glob.glob(os.path.join(d, "log*.txt")) if "_bk" not in os.path.basename(f)]
    if not files:
        sys.exit(f"Nije pronađen dnevnik u {d}")
    return max(files, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--log", help="putanja do log_N.txt (zadano: najnoviji u My Tableau Repository/Logs)")
    ap.add_argument("--last", type=int, default=6, help="koliko zadnjih osvježavanja uzeti (zadano 6)")
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    path = a.log or latest_log(DEFAULT_DIR)
    events = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                j = json.loads(line)
            except ValueError:
                continue
            k = j.get("k", "")
            if k in ("begin-commands-controller.invoke-command", "end-commands-controller.invoke-command",
                     "end-compute-model-task.compute-worksheet-data", "end-visual-controller.update-visual-model"):
                events.append(j)

    # osvježavanja = naredbe refresh-datasource-ui na najvišoj razini
    refreshes = []
    for j in events:
        if j["k"] == "begin-commands-controller.invoke-command" and \
                str(j.get("v", {}).get("args", "")).startswith("tabui:refresh-datasource-ui"):
            refreshes.append({"ts": j["ts"], "id": j.get("a", {}).get("id")})
    if len(refreshes) < a.last:
        sys.exit(f"U dnevniku je pronađeno samo {len(refreshes)} osvježavanja (traženo {a.last}).")
    refreshes = refreshes[-a.last:]

    runs = []
    for i, r in enumerate(refreshes):
        t0 = r["ts"]
        t1 = refreshes[i + 1]["ts"] if i + 1 < len(refreshes) else "9999"
        win = [j for j in events if t0 <= j["ts"] < t1]
        comp = [j["a"]["elapsed"] for j in win if j["k"] == "end-compute-model-task.compute-worksheet-data"]
        vis = [j["a"]["elapsed"] for j in win if j["k"] == "end-visual-controller.update-visual-model"]
        tot = [j["a"]["elapsed"] for j in win if j["k"] == "end-commands-controller.invoke-command"
               and j.get("a", {}).get("id") == r["id"]]
        if not comp or not vis:
            print(f"  osvježavanje u {t0}: nema događaja vizualizacije (je li otvoren list s grafikonom?)")
            continue
        data = max(comp) * 1000
        render = max(max(vis) * 1000 - data, 0)
        runs.append({"ts": t0, "data": data, "render": render, "reload": tot[0] * 1000 if tot else None})

    if len(runs) <= a.warmup:
        sys.exit("Premalo valjanih osvježavanja.")
    print(f"Dnevnik: {path}")
    print(f"Pronađeno {len(runs)} osvježavanja, prvih {a.warmup} odbačeno kao zagrijavanje.")
    out = []
    for i, g in enumerate(runs[a.warmup:], 1):
        rl = f", cijelo osvježavanje {g['reload']:.0f} ms" if g["reload"] is not None else ""
        print(f"  run {i} ({g['ts'][11:19]}): dohvat {g['data']:.1f} ms, crtanje {g['render']:.1f} ms{rl}")
        out += [row("tableau", a.query, i, "data_ms", g["data"], notes="ekstrakt iz CSV-a"),
                row("tableau", a.query, i, "render_ms", g["render"])]
        if g["reload"] is not None:
            out.append(row("tableau", a.query, i, "reload_ms", g["reload"]))
    if a.dry:
        print("(--dry: ništa nije upisano)")
        return
    write_rows(out)
    print(f"Dodano {len(runs) - a.warmup} ponavljanja za {a.query} u results/raw.csv")


if __name__ == "__main__":
    main()
