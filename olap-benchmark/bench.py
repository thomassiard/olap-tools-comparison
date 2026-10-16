#!/usr/bin/env python3
"""
Mjerenje performansi OLAP alata nad Instacart skupom podataka (ClickHouse kao izvor).

Podkomande:
  clickhouse   osnovno (baseline) mjerenje izravno na ClickHouse HTTP sučelju
  superset     vrijeme dohvata podataka preko Superset SQL Lab REST API-ja
  metabase     vrijeme dohvata podataka preko Metabase /api/dataset
  browser      vrijeme crtanja vizualizacije u pregledniku (Playwright), Superset i Metabase
  sysinfo      zapis okoline mjerenja (OS, CPU, RAM, verzije)

Svi rezultati dodaju se u results/raw.csv (dugi format):
  timestamp,tool,query_id,run,metric,value_ms,rows_returned,result_hash,status,notes

Metrike (metric):
  wall_ms    ukupno vrijeme od slanja zahtjeva do primitka rezultata (klijentski sat)
  server_ms  vrijeme koje izvješćuje sam poslužitelj (ClickHouse elapsed / Metabase running_time)
  data_ms    "vrijeme pristupa podacima" koje ulazi u usporedbu (= wall_ms za API alate)
  render_ms  vrijeme crtanja vizualizacije nakon što su podaci stigli
"""
import argparse, csv, hashlib, json, os, platform, random, statistics, string, sys, time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "results", "raw.csv")
FIELDS = ["timestamp", "tool", "query_id", "run", "metric", "value_ms",
          "rows_returned", "result_hash", "status", "notes"]


# ----------------------------------------------------------------- pomoćne funkcije
def load_json(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def all_queries(qdef):
    """Vraća listu (id, sql, skupina). Skalabilnost se širi u S1..S4."""
    out = [(q["id"], q["sql"], "upit") for q in qdef["queries"]]
    sc = qdef["scalability"]
    for s in sc["steps"]:
        out.append((s["id"], sc["template"].format(where=s["where"]).replace("  ", " "), "skalabilnost"))
    return out


def norm_cell(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.6g}"
    s = str(v)
    try:
        return str(int(s))
    except ValueError:
        try:
            f = float(s)
            return str(int(f)) if f.is_integer() else f"{f:.6g}"
        except ValueError:
            return s


def result_hash(rows):
    """Hash neovisan o formatu (dict ili lista) i poretku redaka."""
    norm = []
    for r in rows:
        vals = list(r.values()) if isinstance(r, dict) else list(r)
        norm.append("|".join(norm_cell(x) for x in vals))
    norm.sort()
    return hashlib.md5("\n".join(norm).encode("utf-8")).hexdigest()[:12]


def write_rows(rows):
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    new = not os.path.exists(RAW)
    with open(RAW, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def row(tool, qid, run, metric, value, nrows="", h="", status="ok", notes=""):
    return {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool, "query_id": qid, "run": run, "metric": metric,
            "value_ms": round(value, 3) if value != "" else "", "rows_returned": nrows,
            "result_hash": h, "status": status, "notes": notes}


def summarize(label, values):
    if not values:
        return f"{label}: nema valjanih mjerenja"
    return (f"{label}: medijan {statistics.median(values):.1f} ms "
            f"(min {min(values):.1f}, max {max(values):.1f}, n={len(values)})")


CHECKS = {}   # query_id -> očekivani zbroj zadnjeg stupca (puni se iz queries.json)


def check_sum(qid, rows):
    exp = CHECKS.get(qid)
    if exp is None or not rows:
        return None
    tot = 0
    for r in rows:
        vals = list(r.values()) if isinstance(r, dict) else list(r)
        tot += int(float(norm_cell(vals[-1])))
    return tot == exp


def run_series(tool, queries, runs, warmup, executor, only=None):
    """executor(sql) -> (wall_ms, server_ms|None, rows list)"""
    for qid, sql, _grp in queries:
        if only and qid not in only:
            continue
        data = []
        try:
            for _ in range(warmup):
                executor(sql)
            for i in range(1, runs + 1):
                wall, server, rows = executor(sql)
                h = result_hash(rows)
                if i == 1 and check_sum(qid, rows) is False:
                    print(f"  UPOZORENJE {qid}: zbroj rezultata ne odgovara očekivanom ({CHECKS[qid]})")
                out = [row(tool, qid, i, "wall_ms", wall, len(rows), h),
                       row(tool, qid, i, "data_ms", wall, len(rows), h)]
                if server is not None:
                    out.append(row(tool, qid, i, "server_ms", server, len(rows), h))
                write_rows(out)
                data.append(wall)
            print("  " + summarize(f"{tool} {qid}", data))
        except Exception as e:  # upit nije uspio: zabilježi, nastavi dalje
            print(f"  {tool} {qid}: GREŠKA {e}")
            write_rows([row(tool, qid, 0, "data_ms", "", status="error", notes=str(e)[:200])])


# ----------------------------------------------------------------- ClickHouse
def make_clickhouse(cfg):
    url = cfg["url"].rstrip("/")
    auth = {"user": cfg["user"], "password": cfg["password"]}

    def execute(sql):
        t0 = time.perf_counter()
        r = requests.post(url, params={**auth, "default_format": "JSON"}, data=sql.encode("utf-8"), timeout=600)
        wall = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            raise RuntimeError(r.text[:200])
        j = r.json()
        return wall, j["statistics"]["elapsed"] * 1000, j["data"]
    return execute


# ----------------------------------------------------------------- Metabase
def make_metabase(cfg):
    base = cfg["url"].rstrip("/")
    s = requests.Session()
    r = s.post(f"{base}/api/session", json={"username": cfg["user"], "password": cfg["password"]}, timeout=60)
    r.raise_for_status()
    s.headers["X-Metabase-Session"] = r.json()["id"]

    def execute(sql):
        body = {"database": cfg["database_id"], "type": "native", "native": {"query": sql}}
        t0 = time.perf_counter()
        r = s.post(f"{base}/api/dataset", json=body, timeout=600)
        wall = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        j = r.json()
        if j.get("status") != "completed" or j.get("error"):
            raise RuntimeError(str(j.get("error"))[:200])
        return wall, j.get("running_time"), j["data"]["rows"]
    return execute


# ----------------------------------------------------------------- Superset
def make_superset(cfg):
    base = cfg["url"].rstrip("/")
    s = requests.Session()
    r = s.post(f"{base}/api/v1/security/login",
               json={"username": cfg["user"], "password": cfg["password"], "provider": "db", "refresh": True}, timeout=60)
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    c = s.get(f"{base}/api/v1/security/csrf_token/", timeout=60)
    c.raise_for_status()
    s.headers.update({"X-CSRFToken": c.json()["result"], "Referer": base, "Content-Type": "application/json"})

    def execute(sql):
        cid = "".join(random.choices(string.ascii_letters + string.digits, k=11))
        body = {"database_id": cfg["database_id"], "schema": cfg.get("schema", "instacart"), "sql": sql,
                "runAsync": False, "queryLimit": 10000, "client_id": cid, "tab": "bench",
                "select_as_cta": False, "ctas_method": "TABLE", "expand_data": False}
        t0 = time.perf_counter()
        r = s.post(f"{base}/api/v1/sqllab/execute/", data=json.dumps(body), timeout=600)
        wall = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        j = r.json()
        if j.get("status") not in (None, "success"):
            raise RuntimeError(str(j)[:200])
        return wall, None, j.get("data", [])
    return execute


# ----------------------------------------------------------------- preglednik (vrijeme crtanja)
INIT_JS = """
window.__lastMut = 0;
new MutationObserver(() => { window.__lastMut = performance.now(); })
  .observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
"""


def ui_login(page, tool, base):
    """Prijava u preglednik. Metabase: sesija preko API-ja (kolačić); Superset: obrazac za prijavu."""
    if tool == "metabase":
        r = requests.post(base["url"].rstrip("/") + "/api/session",
                          json={"username": base["user"], "password": base["password"]}, timeout=60)
        r.raise_for_status()
        host = base["url"].split("//", 1)[1].split("/")[0].split(":")[0]
        page.context.add_cookies([{"name": "metabase.SESSION", "value": r.json()["id"],
                                   "domain": host, "path": "/"}])
        return
    page.goto(base["url"].rstrip("/") + "/login/")
    user_sel = ("input[name=username], input#username, input[autocomplete=username], "
                "input[type=text]:visible, input:not([type]):visible")
    page.wait_for_selector("input[type=password]", timeout=30000)
    page.locator(user_sel).first.fill(base["user"])
    page.locator("input[type=password]").first.fill(base["password"])
    page.locator("input[type=password]").first.press("Enter")
    page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
    page.wait_for_load_state("networkidle")


def browser_render(tool, cfg_all, runs, warmup, only):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Instaliraj: pip install playwright && playwright install chromium")
    bcfg = cfg_all["browser"]
    tcfg = bcfg[tool]
    base = cfg_all[tool]
    quiet = bcfg.get("quiet_ms", 600)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bcfg.get("headless", True))
        for qid, url in tcfg["targets"].items():
            if only and qid not in only:
                continue
            vals = []
            for i in range(-warmup + 1, runs + 1):
                ctx = browser.new_context(viewport={"width": 1400, "height": 900})
                ctx.add_init_script(INIT_JS)
                page = ctx.new_page()
                try:
                    # prijava (jednom po kontekstu)
                    ui_login(page, tool, base)
                    t0 = time.perf_counter()
                    page.goto(url, wait_until="commit")
                    page.wait_for_load_state("networkidle")
                    # čekaj tišinu u DOM-u
                    deadline = time.time() + 60
                    while time.time() < deadline:
                        last = page.evaluate("window.__lastMut")
                        now = page.evaluate("performance.now()")
                        if now - last > quiet:
                            break
                        time.sleep(0.1)
                    res = page.evaluate("""(needle) => {
                        const e = performance.getEntriesByType('resource').filter(r => r.name.includes(needle));
                        if (!e.length) return null;
                        const last = e[e.length-1];
                        return {end: last.responseEnd, start: last.startTime};
                    }""", tcfg["data_url_contains"])
                    last = page.evaluate("window.__lastMut")
                    if not res:
                        raise RuntimeError("zahtjev za podacima nije pronađen (provjeri data_url_contains)")
                    render = last - res["end"]
                    data = res["end"] - res["start"]
                    if i >= 1:
                        vals.append(render)
                        write_rows([row(tool, qid, i, "render_ms", max(render, 0)),
                                    row(tool, qid, i, "browser_data_ms", data)])
                except Exception as e:
                    print(f"  {tool} {qid} run {i}: GREŠKA {e}")
                    write_rows([row(tool, qid, i, "render_ms", "", status="error", notes=str(e)[:200])])
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
            print("  " + summarize(f"{tool} {qid} render", vals))
        browser.close()


# ----------------------------------------------------------------- sysinfo
def sysinfo():
    info = {"os": platform.platform(), "python": sys.version.split()[0], "cpu": platform.processor(),
            "cpu_count": os.cpu_count(), "date": datetime.now().isoformat(timespec="seconds")}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        pass
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "sysinfo.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(json.dumps(info, indent=2, ensure_ascii=False))


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["clickhouse", "superset", "metabase", "browser", "sysinfo", "rows"])
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--runs", type=int)
    ap.add_argument("--warmup", type=int)
    ap.add_argument("--only", help="zarezom odvojeni ID-evi upita, npr. Q1,Q4,S2")
    ap.add_argument("--tool", choices=["superset", "metabase"], help="za podkomandu browser")
    a = ap.parse_args()

    if a.cmd == "sysinfo":
        return sysinfo()
    cfg = json.load(open(a.config, encoding="utf-8"))
    runs = a.runs or cfg.get("runs", 10)
    warm = a.warmup if a.warmup is not None else cfg.get("warmup", 1)
    only = set(a.only.split(",")) if a.only else None
    qdef = load_json("queries.json")
    queries = all_queries(qdef)
    for q in qdef["queries"]:
        if "check" in q:
            CHECKS[q["id"]] = q["check"]["sum_n"]

    if a.cmd == "rows":  # stvarni broj redaka u podskupovima S1..S4 (za os x na grafu skalabilnosti)
        ex = make_clickhouse(cfg["clickhouse"])
        sc = qdef["scalability"]
        out = {}
        for st in sc["steps"]:
            _, _, rows = ex(sc["rows_template"].format(where=st["where"]))
            out[st["id"]] = int(norm_cell(list(rows[0].values())[0]))
        with open(os.path.join(HERE, "results", "scale_rows.json"), "w") as f:
            json.dump(out, f, indent=2)
        print(out)
        return

    if a.cmd == "browser":
        if not a.tool:
            sys.exit("--tool superset|metabase je obavezan")
        return browser_render(a.tool, cfg, runs, warm, only)

    maker = {"clickhouse": make_clickhouse, "superset": make_superset, "metabase": make_metabase}[a.cmd]
    ex = maker(cfg[a.cmd])
    print(f"== {a.cmd}: {runs} ponavljanja + {warm} zagrijavanje po upitu")
    run_series(a.cmd, queries, runs, warm, ex, only)
    print(f"Rezultati dodani u {RAW}")


if __name__ == "__main__":
    main()
