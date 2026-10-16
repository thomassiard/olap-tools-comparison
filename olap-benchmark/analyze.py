#!/usr/bin/env python3
"""
Obrada rezultata iz results/raw.csv  ->  tablice, grafikoni i automatske ocjene za rad.

  python analyze.py

Izlaz (results/):
  summary.csv              n, medijan, min, max, Q1, Q3, CV po alatu / upitu / metrici
  table_data_ms.csv        medijan vremena dohvata podataka [ms]
  table_render_ms.csv      medijan vremena generiranja vizualizacije [ms]
  table_total_ms.csv       medijan ukupnog vremena do prikaza (dohvat + crtanje) [ms]
  table_ratio.csv          omjer ukupnog vremena prema najbržem vizualizacijskom alatu po upitu
  scores_auto.json         ocjene K3 (brzina) i K8 (skalabilnost) prema pravilima iz Tablice 4
  consistency.txt          provjera da alati vraćaju jednak rezultat (sažetak skupa redaka)
  fig_total_time.png, fig_data_time.png, fig_render_time.png, fig_scalability.png, fig_heatmap.png

Pravila čišćenja (dokumentirano i u radu):
  * koriste se samo retci sa status = ok;
  * po (alat, upit, metrika) zadržava se zadnjih N mjerenja (N = 10 automatski, 5 ručno),
    čime se isključuju probna pokretanja skripte prije glavnog mjerenja;
  * Power BI S4: upit S4 identičan je upitu Q7 (cijela tablica, bez filtra), pa se koriste vrijednosti Q7;
  * Tableau Public: Q6-Q9 i S4 nisu izvedivi (izvor > 15 M redaka) i bilježe se kao n/p.
"""
import json, math, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
TOOLS = ["clickhouse", "superset", "metabase", "powerbi", "tableau"]
VIZ = ["superset", "metabase", "powerbi", "tableau"]
LABEL = {"clickhouse": "ClickHouse (osnovna linija)", "superset": "Apache Superset", "metabase": "Metabase",
         "powerbi": "Power BI", "tableau": "Tableau Public"}
SHORT = {"clickhouse": "ClickHouse", "superset": "Superset", "metabase": "Metabase", "powerbi": "Power BI",
         "tableau": "Tableau Public"}
# kategorijska paleta (provjerena za razlikovanje kod daltonizma); ClickHouse = neutralna siva osnovna linija
COLOR = {"clickhouse": "#8a8984", "superset": "#2a78d6", "metabase": "#1baf7a", "powerbi": "#eda100",
         "tableau": "#eb6834"}
RUNS = {"clickhouse": 10, "superset": 10, "metabase": 10, "powerbi": 5, "tableau": 5}
QUERIES = [f"Q{i}" for i in range(1, 10)]
SCALE = ["S1", "S2", "S3", "S4"]
INK, INK2, GRID = "#1f1f1e", "#5f5e5a", "#e6e5e0"
plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.dpi": 220, "savefig.bbox": "tight"})


def hr(x, d=0):
    """Hrvatski zapis broja (decimalni zarez, točka za tisućice)."""
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def load():
    df = pd.read_csv(os.path.join(RES, "raw.csv"))
    df = df[(df["status"] == "ok") & df["value_ms"].notna()].copy()
    df["value_ms"] = df["value_ms"].astype(float)
    df = df.sort_values("timestamp", kind="stable")
    rank = df.groupby(["tool", "query_id", "metric"]).cumcount(ascending=False)  # 0 = zadnje mjerenje
    df = df[rank < df["tool"].map(RUNS).fillna(10)]
    pb = df[(df.tool == "powerbi") & (df.query_id == "Q7")].copy()
    if not pb.empty and df[(df.tool == "powerbi") & (df.query_id == "S4")].empty:
        pb["query_id"] = "S4"; pb["notes"] = "jednako Q7"
        df = pd.concat([df, pb])
    return df


def stats(df):
    g = df.groupby(["tool", "query_id", "metric"])["value_ms"]
    s = g.agg(n="count", median="median", min="min", max="max", mean="mean", std="std").reset_index()
    q = g.quantile([0.25, 0.75]).unstack().reset_index()
    q.columns = ["tool", "query_id", "metric", "q1", "q3"]
    s = s.merge(q, on=["tool", "query_id", "metric"])
    s["cv_pct"] = (s["std"] / s["mean"] * 100).round(1)
    return s


def matrix(s, metric):
    M = pd.DataFrame(index=TOOLS, columns=QUERIES + SCALE, dtype=float)
    for _, r in s[s.metric == metric].iterrows():
        if r.tool in M.index and r.query_id in M.columns:
            M.loc[r.tool, r.query_id] = r["median"]
    return M


def save_table(M, name, digits=1):
    out = M.copy()
    out.index = [LABEL[t] for t in out.index]
    out.round(digits).to_csv(os.path.join(RES, name), index_label="alat")


def grouped_bars(M, tools, title, fname, ylabel, note=None):
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    n = len(tools); w = 0.82 / n
    x = np.arange(len(QUERIES))
    for i, t in enumerate(tools):
        vals = M.loc[t, QUERIES].values.astype(float)
        xs = x - 0.41 + w * (i + 0.5)
        ax.bar(xs, np.where(np.isnan(vals), 0, vals), w * 0.86, label=SHORT[t], color=COLOR[t], zorder=3)
    ax.set_yscale("log")
    lo = np.nanmin(M.loc[tools, QUERIES].values.astype(float))
    ax.set_ylim(max(lo / 2, 1), None)
    for i, t in enumerate(tools):  # oznaka n/p nakon postavljanja ljestvice
        vals = M.loc[t, QUERIES].values.astype(float)
        for xi, v in zip(x - 0.41 + w * (i + 0.5), vals):
            if np.isnan(v):
                ax.text(xi, ax.get_ylim()[0] * 1.15, "n/p", rotation=90, ha="center", va="bottom", fontsize=6.5, color=INK2)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: hr(v)))
    ax.set_xticks(x); ax.set_xticklabels(QUERIES)
    ax.set_ylabel(ylabel); ax.set_xlabel("Upit (opis u Tablici 5; Q6-Q9 obrađuju 32,4 M zapisa)")
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    ax.grid(axis="y", color=GRID, zorder=0, which="both", lw=0.6)
    ax.legend(fontsize=7.5, ncol=len(tools), frameon=False, loc="upper left", bbox_to_anchor=(0, -0.2))
    fig.savefig(os.path.join(RES, fname)); plt.close(fig)


def fig_scal(T, rows, fname):
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for t in TOOLS:
        xs = [rows[s] for s in SCALE if not np.isnan(T.loc[t, s])]
        ys = [T.loc[t, s] for s in SCALE if not np.isnan(T.loc[t, s])]
        if not xs:
            continue
        ax.plot(xs, ys, marker="o", ms=5, lw=2, color=COLOR[t], label=SHORT[t], zorder=3,
                markeredgecolor="white", markeredgewidth=1)
        dy = {"superset": 6, "powerbi": -7}.get(t, 0)
        ax.annotate(SHORT[t], (xs[-1], ys[-1]), xytext=(7, dy), textcoords="offset points",
                    fontsize=7.5, color=INK, va="center")
    if np.isnan(T.loc["tableau", "S4"]):
        ax.axvline(15e6, color=INK2, lw=0.8, ls="--", zorder=1)
        ax.text(15e6 * 1.05, 25, "granica Tableau Public\n(15 M redaka)", fontsize=7, color=INK2, va="center")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(7e5, 1.1e8)
    from matplotlib.ticker import FuncFormatter, NullFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: hr(v)))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([10, 20, 50, 100, 200, 500, 1000])
    ax.set_xticks([1e6, 5e6, 1e7, 3.24e7]); ax.set_xticklabels(["1 M", "5 M", "10 M", "32,4 M"])
    ax.set_xlabel("Broj obrađenih redaka (S1-S4, log. ljestvica)")
    ax.set_ylabel("Ukupno vrijeme do prikaza [ms] (log.)")
    ax.set_title("Skalabilnost: isti upit nad rastućim podskupom tablice", fontsize=10, color=INK, loc="left")
    ax.grid(color=GRID, which="both", lw=0.6, zorder=0)
    ax.legend(fontsize=7.5, frameon=False, ncol=5, loc="upper left", bbox_to_anchor=(0, -0.17))
    fig.savefig(os.path.join(RES, fname)); plt.close(fig)


def fig_heat(R, fname):
    tools = VIZ
    M = R.loc[tools, QUERIES].values.astype(float)
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    L = np.log10(M)
    ax.imshow(np.ma.masked_invalid(L), cmap="Oranges", aspect="auto", vmin=0, vmax=max(1.2, np.nanmax(L)))
    ax.set_xticks(range(len(QUERIES))); ax.set_xticklabels(QUERIES)
    ax.set_yticks(range(len(tools))); ax.set_yticklabels([SHORT[t] for t in tools])
    for i in range(len(tools)):
        for j in range(len(QUERIES)):
            v = M[i, j]
            ax.text(j, i, "n/p" if np.isnan(v) else (hr(v, 1) + "×"), ha="center", va="center", fontsize=7.5,
                    color="white" if (not np.isnan(v) and np.log10(v) > 0.8) else INK)
    ax.set_title("Ukupno vrijeme u odnosu na najbrži vizualizacijski alat po upitu (1,0× = najbrži)",
                 fontsize=10, color=INK, loc="left")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.savefig(os.path.join(RES, fname)); plt.close(fig)


def score_speed(r):
    return 5 if r <= 1.25 else 4 if r <= 1.75 else 3 if r <= 2.5 else 2 if r <= 4 else 1


def score_scal(b):
    return 5 if b <= 0.6 else 4 if b <= 0.8 else 3 if b <= 1.0 else 2 if b <= 1.3 else 1


def main():
    df = load()
    s = stats(df)
    s.round(2).to_csv(os.path.join(RES, "summary.csv"), index=False)

    D, Rn = matrix(s, "data_ms"), matrix(s, "render_ms")
    T = D + Rn.fillna(0)
    T.loc["clickhouse"] = D.loc["clickhouse"]
    save_table(D, "table_data_ms.csv"); save_table(Rn, "table_render_ms.csv"); save_table(T, "table_total_ms.csv")

    best = T.loc[VIZ, QUERIES].min(axis=0)
    R = T.loc[TOOLS, QUERIES] / best
    save_table(R, "table_ratio.csv", 2)

    rows = json.load(open(os.path.join(RES, "scale_rows.json")))
    sc = {}
    for t in TOOLS:
        o = {}
        if t in VIZ:
            r = R.loc[t, QUERIES].dropna()
            gm = float(np.exp(np.log(r).mean()))
            o["k3_geo_ratio"] = round(gm, 3); o["k3_queries"] = list(r.index); o["K3"] = score_speed(gm)
        pts = [(math.log(rows[x]), math.log(T.loc[t, x])) for x in SCALE if not np.isnan(T.loc[t, x])]
        if len(pts) >= 2:
            b = float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0])
            o["k8_slope_b"] = round(b, 3)
        full = not np.isnan(T.loc[t, "S4"])
        o["K8"] = score_scal(o["k8_slope_b"]) if (full and "k8_slope_b" in o) else 1
        o["k8_full_dataset"] = full
        sc[t] = o
    json.dump(sc, open(os.path.join(RES, "scores_auto.json"), "w"), indent=2, ensure_ascii=False)

    # konzistentnost: sažetak (hash) normaliziranog skupa redaka po upitu
    h = df[(df.metric == "data_ms") & df.result_hash.notna()].groupby(["query_id", "tool"]).result_hash.agg(set)
    lines = []
    for q in QUERIES + SCALE:
        per = {t: h.get((q, t), set()) for t in ["clickhouse", "superset", "metabase"]}
        allh = set().union(*per.values())
        ok = len(allh) == 1 and all(len(v) == 1 for v in per.values())
        lines.append(f"{q}: {'JEDNAK' if ok else 'RAZLIČIT'} rezultat u ClickHouseu, Supersetu i Metabaseu ({next(iter(allh)) if ok else allh})")
    lines.append("Power BI i Tableau Public: rezultati provjereni ručno (ukupni zbroj u statusnoj traci / tablici, npr. Q8 = 32.434.489).")
    open(os.path.join(RES, "consistency.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    grouped_bars(T, TOOLS, "Ukupno vrijeme do prikaza po upitu i alatu (medijan)", "fig_total_time.png",
                 "Vrijeme [ms] (log. ljestvica)",
                 "ClickHouse: samo dohvat (nema vizualizacije). n/p = Tableau Public ne može učitati izvor od 32,4 M redaka.")
    grouped_bars(D, TOOLS, "Vrijeme dohvata podataka po upitu i alatu (medijan)", "fig_data_time.png",
                 "Vrijeme [ms] (log. ljestvica)",
                 "Tableau Public: upit nad lokalnim ekstraktom (CSV), nije izravno usporediv s alatima koji šalju upit bazi.")
    grouped_bars(Rn, VIZ, "Vrijeme generiranja vizualizacije po upitu i alatu (medijan)", "fig_render_time.png",
                 "Vrijeme [ms] (log. ljestvica)")
    fig_scal(T, rows, "fig_scalability.png")
    fig_heat(R, "fig_heatmap.png")

    print("Medijan ukupnog vremena [ms]:")
    print(T.round(0).to_string())
    print("\nOcjene:", json.dumps({t: {k: v for k, v in o.items() if k in ("K3", "K8")} for t, o in sc.items()}, ensure_ascii=False))
    print("Rezultati u", RES)


if __name__ == "__main__":
    main()
