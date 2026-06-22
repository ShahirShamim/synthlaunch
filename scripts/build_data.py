"""Rebuild the bundled demo datasets (stdlib only — no deps needed).

  python scripts/build_data.py

1. Downloads the real California Prop 99 panel (Abadie/Diamond/Hainmueller 2010)
   and writes it in SynthLaunch tidy form: date, unit_id, metric.
2. Downloads real UK GDP-per-capita data (World Bank) to build the Brexit
   synthetic-control panel: UK vs OECD donor economies, treatment 2016.
3. Generates a synthetic B2B-marketplace panel with a KNOWN injected effect so the
   engine's ground-truth recovery can be tested.
"""
import csv
import io
import json
import math
import random
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend" / "data"
SRC_URL = ("https://raw.githubusercontent.com/matheusfacure/python-causality-handbook/"
           "master/causal-inference-for-the-brave-and-true/data/smoking.csv")

STATE_NAMES = {
    1: "Alabama", 2: "Arkansas", 3: "California", 4: "Colorado", 5: "Connecticut",
    6: "Delaware", 7: "Georgia", 8: "Idaho", 9: "Illinois", 10: "Indiana",
    11: "Iowa", 12: "Kansas", 13: "Kentucky", 14: "Louisiana", 15: "Maine",
    16: "Minnesota", 17: "Mississippi", 18: "Missouri", 19: "Montana", 20: "Nebraska",
    21: "Nevada", 22: "New Hampshire", 23: "New Mexico", 24: "North Carolina",
    25: "North Dakota", 26: "Ohio", 27: "Oklahoma", 28: "Pennsylvania",
    29: "Rhode Island", 30: "South Carolina", 31: "South Dakota", 32: "Tennessee",
    33: "Texas", 34: "Utah", 35: "Vermont", 36: "Virginia", 37: "West Virginia",
    38: "Wisconsin", 39: "Wyoming",
}


def build_prop99():
    raw = urllib.request.urlopen(SRC_URL, timeout=30).read().decode()
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = [{"date": f"{int(r['year'])}-01-01",
            "unit_id": STATE_NAMES[int(r["state"])],
            "metric": round(float(r["cigsale"]), 2)} for r in rows]
    out.sort(key=lambda x: (x["unit_id"], x["date"]))
    _write("prop99_california.csv", out)
    print(f"prop99_california.csv: {len(out)} rows, {len({o['unit_id'] for o in out})} units")


def build_brexit():
    """UK GDP per capita vs a donor pool of advanced economies (World Bank,
    constant 2015 US$). The 2016 EU-referendum is the intervention — the famous
    'cost of Brexit' synthetic-control case (Born et al. 2019)."""
    indicator = "NY.GDP.PCAP.KD"
    years = list(range(1995, 2020))  # 21 pre (1995-2015) + 4 post (2016-2019)
    # GBR treated; donors = OECD advanced economies (Born et al. donor pool).
    iso = ["GBR", "AUS", "AUT", "BEL", "CAN", "CHE", "DNK", "FIN", "FRA", "DEU",
           "ISL", "IRL", "ITA", "JPN", "LUX", "NLD", "NZL", "NOR", "PRT", "ESP",
           "SWE", "USA"]
    panel = {}
    names = {}
    for code in iso:
        url = (f"https://api.worldbank.org/v2/country/{code}/indicator/{indicator}"
               f"?format=json&per_page=400&date={years[0]}:{years[-1]}")
        data = json.loads(urllib.request.urlopen(url, timeout=30).read())
        series = {}
        for o in (data[1] or []):
            if o["value"] is not None:
                series[int(o["date"])] = float(o["value"])
            names[code] = o["country"]["value"]
        panel[code] = series
    # keep only countries with complete coverage -> balanced panel, and rebase each
    # to an index (base year = 100) so SCM matches comparable GROWTH paths rather
    # than absolute levels (Luxembourg ~90k vs Portugal ~20k would otherwise dominate).
    base = years[0]
    rows = []
    kept = []
    for code in iso:
        if all(y in panel[code] for y in years):
            kept.append(code)
            b = panel[code][base]
            for y in years:
                rows.append({"date": f"{y}-01-01", "unit_id": names[code],
                             "metric": round(panel[code][y] / b * 100.0, 3)})
    rows.sort(key=lambda x: (x["unit_id"], x["date"]))
    _write("brexit_uk.csv", rows)
    dropped = [c for c in iso if c not in kept]
    print(f"brexit_uk.csv: {len(rows)} rows, {len(kept)} units"
          + (f" (dropped for gaps: {dropped})" if dropped else ""))


def build_synthetic():
    random.seed(42)
    donors = ["Berlin", "Madrid", "Amsterdam", "Paris", "Milan",
              "Dublin", "Lisbon", "Vienna", "Warsaw", "Prague"]
    months, y, m = [], 2023, 1
    for _ in range(36):
        months.append(f"{y}-{m:02d}-01")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    interv, effect = "2025-01-01", -0.08
    factor = [100 + 0.8 * i + 6 * math.sin(2 * math.pi * i / 12) for i in range(36)]
    levels = {d: random.uniform(0.7, 1.4) for d in donors}
    series = {d: [round(levels[d] * factor[i] + random.gauss(0, 2.0), 2) for i in range(36)]
              for d in donors}
    combo = {"Berlin": 0.5, "Madrid": 0.3, "Amsterdam": 0.2}
    london_cf = [sum(w * series[d][i] for d, w in combo.items()) + random.gauss(0, 1.5)
                 for i in range(36)]
    london, post_eff = [], []
    for i in range(36):
        if months[i] >= interv:
            london.append(round(london_cf[i] * (1 + effect), 2))
            post_eff.append(london_cf[i] * effect)
        else:
            london.append(round(london_cf[i], 2))
    rows = [{"date": months[i], "unit_id": d, "metric": series[d][i]}
            for d in donors for i in range(36)]
    rows += [{"date": months[i], "unit_id": "London", "metric": london[i]} for i in range(36)]
    rows.sort(key=lambda x: (x["unit_id"], x["date"]))
    _write("synthetic_marketplace.csv", rows)
    print(f"synthetic_marketplace.csv: {len(rows)} rows, true ATT = {sum(post_eff)/len(post_eff):.3f}")


def _write(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "unit_id", "metric"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    build_prop99()
    build_brexit()
    build_synthetic()
    print("done ->", OUT)
