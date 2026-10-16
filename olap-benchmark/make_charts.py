#!/usr/bin/env python3
"""
Automatski izrađuje po jedan grafikon za svaki upit (Q1-Q9, S1-S4) u Supersetu i Metabaseu
i upisuje njihove URL-ove u config.json -> browser.<alat>.targets, kako bi se
`python bench.py browser --tool superset|metabase` moglo odmah pokrenuti.

Upotreba:
  python make_charts.py superset
  python make_charts.py metabase
  python make_charts.py all

Ponovno pokretanje je sigurno: postojeći grafikoni istog naziva (bench_Q1 ...) se ponovno koriste.
"""
import json, os, sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")

# Kako se svaki rezultat prikazuje: None = jedna vrijednost (broj), inače (x os, serija ili None)
LAYOUT = {
    "Q1": None, "Q3": None, "Q6": None,
    "Q2": ("department", None),
    "Q4": ("order_hour_of_day", "order_dow"),
    "Q5": ("aisle", None),
    "Q7": ("product_id", None),
    "Q8": ("department", None),
    "Q9": ("department", "order_dow"),
    "S1": ("product_id", None), "S2": ("product_id", None),
    "S3": ("product_id", None), "S4": ("product_id", None),
}


def load_queries():
    with open(os.path.join(HERE, "queries.json"), encoding="utf-8") as f:
        qdef = json.load(f)
    out = [(q["id"], q["sql"]) for q in qdef["queries"]]
    sc = qdef["scalability"]
    for s in sc["steps"]:
        out.append((s["id"], sc["template"].format(where=s["where"]).replace("  ", " ")))
    return out


# ----------------------------------------------------------------- Superset
def superset(cfg, queries):
    base = cfg["url"].rstrip("/")
    s = requests.Session()
    r = s.post(f"{base}/api/v1/security/login",
               json={"username": cfg["user"], "password": cfg["password"], "provider": "db", "refresh": True}, timeout=60)
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    c = s.get(f"{base}/api/v1/security/csrf_token/", timeout=60)
    c.raise_for_status()
    s.headers.update({"X-CSRFToken": c.json()["result"], "Referer": base})

    def find(endpoint, col, value):
        q = json.dumps({"filters": [{"col": col, "opr": "eq", "value": value}]})
        r = s.get(f"{base}/api/v1/{endpoint}/", params={"q": q}, timeout=60)
        r.raise_for_status()
        res = r.json().get("result", [])
        return res[0]["id"] if res else None

    targets = {}
    for qid, sql in queries:
        name = f"bench_{qid}"
        ds = find("dataset", "table_name", name)
        if ds is None:
            r = s.post(f"{base}/api/v1/dataset/", json={
                "database": cfg["database_id"], "schema": cfg.get("schema", "instacart"),
                "table_name": name, "sql": sql}, timeout=120)
            if r.status_code >= 400:
                print(f"  {qid}: GREŠKA pri izradi dataseta: {r.text[:300]}")
                continue
            ds = r.json()["id"]
            # osvježi popis stupaca
            s.put(f"{base}/api/v1/dataset/{ds}/refresh", timeout=120)

        metric = {"expressionType": "SIMPLE", "column": {"column_name": "n"}, "aggregate": "SUM", "label": "n"}
        lay = LAYOUT[qid]
        if lay is None:
            viz = "big_number_total"
            params = {"viz_type": viz, "datasource": f"{ds}__table", "metric": metric, "adhoc_filters": []}
        else:
            x, series = lay
            viz = "echarts_timeseries_bar"
            params = {"viz_type": viz, "datasource": f"{ds}__table", "x_axis": x, "metrics": [metric],
                      "groupby": [series] if series else [], "adhoc_filters": [], "row_limit": 10000,
                      "xAxisForceCategorical": True, "orientation": "vertical", "order_desc": True,
                      "show_legend": bool(series)}

        ch = find("chart", "slice_name", name)
        if ch is None:
            r = s.post(f"{base}/api/v1/chart/", json={
                "slice_name": name, "viz_type": viz, "datasource_id": ds, "datasource_type": "table",
                "params": json.dumps(params)}, timeout=60)
            if r.status_code >= 400:
                print(f"  {qid}: GREŠKA pri izradi grafikona: {r.text[:300]}")
                continue
            ch = r.json()["id"]
        targets[qid] = f"{base}/explore/?slice_id={ch}"
        print(f"  superset {qid}: grafikon {ch} -> {targets[qid]}")
    return targets


# ----------------------------------------------------------------- Metabase
def metabase(cfg, queries):
    base = cfg["url"].rstrip("/")
    s = requests.Session()
    r = s.post(f"{base}/api/session", json={"username": cfg["user"], "password": cfg["password"]}, timeout=60)
    r.raise_for_status()
    s.headers["X-Metabase-Session"] = r.json()["id"]

    existing = {}
    r = s.get(f"{base}/api/card", timeout=60)
    if r.ok:
        for card in r.json():
            existing[card.get("name")] = card["id"]

    targets = {}
    for qid, sql in queries:
        name = f"bench_{qid}"
        cid = existing.get(name)
        if cid is None:
            lay = LAYOUT[qid]
            if lay is None:
                display, vis = "scalar", {}
            else:
                x, series = lay
                display = "bar"
                vis = {"graph.dimensions": [x] + ([series] if series else []), "graph.metrics": ["n"]}
            r = s.post(f"{base}/api/card", json={
                "name": name, "display": display, "visualization_settings": vis,
                "dataset_query": {"database": cfg["database_id"], "type": "native", "native": {"query": sql}}},
                timeout=60)
            if r.status_code >= 400:
                print(f"  {qid}: GREŠKA pri izradi pitanja: {r.text[:300]}")
                continue
            cid = r.json()["id"]
        targets[qid] = f"{base}/question/{cid}"
        print(f"  metabase {qid}: pitanje {cid} -> {targets[qid]}")
    return targets


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    queries = load_queries()
    tools = ["superset", "metabase"] if which == "all" else [which]
    for tool in tools:
        print(f"== {tool}")
        t = superset(cfg["superset"], queries) if tool == "superset" else metabase(cfg["metabase"], queries)
        if t:
            cfg["browser"][tool]["targets"] = t
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("URL-ovi upisani u config.json -> browser.<alat>.targets")


if __name__ == "__main__":
    main()
