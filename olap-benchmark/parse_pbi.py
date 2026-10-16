#!/usr/bin/env python3
"""
Pretvara izvoz iz Power BI Performance Analyzera (JSON) u retke za results/raw.csv.

Postupak (po upitu): jedna stranica s JEDNOM vizualizacijom za taj upit -> Optimize > Performance analyzer
-> Start recording -> 6 puta "Refresh visuals" (prvo je zagrijavanje) -> Stop -> Export -> npr. pbi_Q4.json

  python parse_pbi.py pbi_Q4.json --query Q4          # upiše 5 ponavljanja u results/raw.csv
  python parse_pbi.py pbi_Q4.json --query Q4 --dry    # samo ispiše, ne upisuje

Struktura događaja (Power BI Desktop 2026): svako osvježavanje ima događaj "Visual Container Lifecycle",
a pod njim "Query" (od slanja upita do primitka rezultata; uključuje "Execute DAX Query" i
"Execute Direct Query" prema ClickHouseu) i "Render" (iscrtavanje vizualizacije).
  data_ms   = trajanje događaja "Query"
  render_ms = trajanje događaja "Render"
  server_ms = trajanje događaja "Execute Direct Query" (vrijeme upita u izvoru, informativno)
"""
import argparse, json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import row, write_rows  # noqa


def ts(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00"))


def dur(e):
    return (ts(e["end"]) - ts(e["start"])).total_seconds() * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--query", required=True)
    ap.add_argument("--warmup", type=int, default=1, help="koliko prvih osvježavanja odbaciti (zadano 1)")
    ap.add_argument("--dry", action="store_true", help="samo ispiši, ne upisuj u raw.csv")
    a = ap.parse_args()

    ev = json.load(open(a.file, encoding="utf-8-sig")).get("events", [])
    children = {}
    for e in ev:
        children.setdefault(e.get("parentId"), []).append(e)

    def descendants(eid):
        out, stack = [], [eid]
        while stack:
            for c in children.get(stack.pop(), []):
                out.append(c)
                stack.append(c["id"])
        return out

    lifecycles = sorted([e for e in ev if e.get("name") == "Visual Container Lifecycle" and "end" in e],
                        key=lambda e: e["start"])
    if not lifecycles:
        sys.exit("Nije pronađen nijedan događaj 'Visual Container Lifecycle'.")
    titles = {e.get("metrics", {}).get("visualTitle") for e in lifecycles}
    if len(titles) > 1:
        print(f"UPOZORENJE: u izvozu je više vizualizacija {titles}; na stranici treba biti samo jedna.")

    runs = []
    for lc in lifecycles:
        kids = {c["name"]: c for c in children.get(lc["id"], []) if "end" in c}
        if "Query" not in kids or "Render" not in kids:
            continue
        dq = [d for d in descendants(lc["id"]) if d.get("name") == "Execute Direct Query" and "end" in d]
        runs.append({"data": dur(kids["Query"]), "render": dur(kids["Render"]),
                     "server": sum(dur(d) for d in dq) if dq else None})

    if len(runs) <= a.warmup:
        sys.exit(f"Pronađeno samo {len(runs)} osvježavanja; potrebno barem {a.warmup + 1}.")
    print(f"Pronađeno {len(runs)} osvježavanja, prvih {a.warmup} odbačeno kao zagrijavanje.")
    out = []
    for i, g in enumerate(runs[a.warmup:], 1):
        srv = f", izvor {g['server']:.1f} ms" if g["server"] is not None else ""
        print(f"  run {i}: dohvat {g['data']:.1f} ms, crtanje {g['render']:.1f} ms{srv}")
        out += [row("powerbi", a.query, i, "data_ms", g["data"]),
                row("powerbi", a.query, i, "render_ms", g["render"])]
        if g["server"] is not None:
            out.append(row("powerbi", a.query, i, "server_ms", g["server"]))
    if a.dry:
        print("(--dry: ništa nije upisano)")
        return
    write_rows(out)
    print(f"Dodano {len(runs) - a.warmup} ponavljanja za {a.query} u results/raw.csv")


if __name__ == "__main__":
    main()
