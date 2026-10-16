#!/usr/bin/env python3
"""
Izrađuje usporedni grafikon (broj narudžbi po danu u tjednu, order_dow) u Supersetu i Metabaseu
za potpoglavlje 5.7 (usporedne vizualizacije). Isti SQL, ista vrsta grafikona (stupčasti).

  python make_compare.py
"""
import json, os
import make_charts as mc

SQL = "SELECT order_dow, count() AS n FROM instacart.orders GROUP BY order_dow ORDER BY order_dow"


def main():
    with open(mc.CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    mc.LAYOUT["CMP"] = ("order_dow", None)
    q = [("CMP", SQL)]
    s = mc.superset(cfg["superset"], q)
    m = mc.metabase(cfg["metabase"], q)
    print("\nOtvori i snimi zaslon:")
    for k, v in {**{"Superset": s.get("CMP")}, **{"Metabase": m.get("CMP")}}.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
