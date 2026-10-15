"""
Prepare chart-ready data for "Built Brick by Brick" (FIT3179 DV2).

Put the raw downloads in data_prep/raw/ (see README.md for links), then run:

    python data_prep/prepare_data.py

Every output goes to data/ and is small enough for GitHub Pages.
Each step prints what it matched and what it dropped, so you can check
the joins before building charts. Edit the CONFIG section to suit your story.
"""
import csv
import json
import math
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.environ.get("LEGO_RAW_DIR", os.path.join(HERE, "raw"))
OUT = os.path.join(HERE, "..", "data")
PROJECT = os.path.join(HERE, "..")

# ---------------------------------------------------------------- CONFIG
# One stated exchange rate, used everywhere. Replace with the rate you cite
# (e.g. from DOSM's Monthly Statistical Bulletin) and keep it in sync with the
# "usd_to_rm" param in specs that convert prices.
USD_TO_RM = 4.09

# The six theme groups used on every chart, in display order.
GROUPS = ["Licensed", "Modern day", "Action/Adventure", "Historical", "Technical", "Young children", "Other"]

# How Maven's themeGroup values collapse into the six groups. Anything not
# listed becomes "Other". Check the printed list of themeGroup values and adjust.
GROUP_MAP = {
    "Licensed": "Licensed",
    "Modern day": "Modern day",
    "Action/Adventure": "Action/Adventure",
    "Historical": "Historical",
    "Technical": "Technical",
    "Model making": "Technical",
    # Extra mappings; delete any you disagree with and explain your choices on the page.
    "Constraction": "Action/Adventure",   # Bionicle, Hero Factory and similar
    "Racing": "Action/Adventure",
    "Girls": "Modern day",                # Belville, Scala and similar
    "Educational": "Technical",
    "Pre-school": "Young children",       # Duplo and similar
    "Junior": "Young children",
    # Miscellaneous, Basic, Vintage and Art and crafts stay in "Other".
}

# Keep only proper sets. Maven's "category" column marks real sets as "Normal";
# other categories include gear, books and collections. Set to None to keep everything.
KEEP_CATEGORIES = ["Normal"]

# Rebrickable has no category column. Sets with fewer parts than this are dropped
# (gear, books, key chains and similar usually have 0 or very few parts).
REBRICKABLE_MIN_PARTS = 1

# Rebrickable top-level themes that are not real sets; dropped to match the Maven "Normal" filter.
REBRICKABLE_EXCLUDE = ["Gear", "Books", "LEGO Brand Store", "Collectible Minifigures"]

# Rebrickable top-level themes whose group cannot be borrowed from Maven by name
# (different spelling, or released after Maven's data ends in 2022).
REBRICKABLE_GROUP_OVERRIDES = {
    "Super Heroes Marvel": "Licensed",
    "Super Heroes DC": "Licensed",
    "Pokémon": "Licensed",
    "Sonic The Hedgehog": "Licensed",
    "Animal Crossing": "Licensed",
    "Unikitty!": "Licensed",
    "One Piece": "Licensed",
    "Fortnite": "Licensed",
    "Gabby's Dollhouse": "Licensed",
    "Wicked": "Licensed",
    "Bluey": "Licensed",
    "Train": "Modern day",
    "Boat": "Modern day",
    "Dreamzzz": "Action/Adventure",
    "Dino Attack / Dino 2010": "Action/Adventure",
    "Ninja": "Historical",
    "Educational and Dacta": "Technical",
    "FIRST LEGO League": "Technical",
    "LEGO Ideas and CUUSOO": "Technical",
    "BrickLink Designer Program": "Technical",
    "Botanicals": "Technical",
    "Modular Buildings": "Technical",
    "System": "Other",
    "Make & Create": "Other",
}

# Themes shown in the Gantt chart (chart 4). Matched against Rebrickable theme
# names at any level of the theme tree.
GANTT_THEMES = ["Castle", "Pirates", "Western", "Adventurers", "Vikings",
                "Pharaoh's Quest", "Ninjago", "Monkie Kid", "Chinese Traditional Festivals"]
GANTT_MAX_GAP = 1  # years without sets that still count as one continuous run
GANTT_MIN_RUN_SETS = 3  # drop runs with fewer sets than this (one-off promotional items)

# Complete years only. Rebrickable includes the current, unfinished year and
# pre-announced sets; Maven starts in 1970.
YEAR_MIN, YEAR_MAX = 1970, 2025

# Flagship sets for the isotype chart (chart 9). Leave empty to use the five
# sets with the most minifigures; otherwise list Maven set_id values.
FLAGSHIP_SET_IDS = ["71043-1", "75159-1", "71741-1", "10305-1", "21337-1"]

# Price of the flagship set used for the affordability cartogram (map 2), in USD.
# None means "use the median price of the flagship sets".
FLAGSHIP_PRICE_USD = 399.99

# Where the TopoJSON boundary files live, relative to the project folder, and
# what they are called. Mapshaper may have saved them as .json; use the real names.
# The object (layer) names are the names right after "objects": in each file.
TOPO_DIR = "js"
DISTRICTS_FILE, DISTRICTS_OBJECT = "malaysia_districts.topojson", "districts"
STATES_FILE, STATES_OBJECT = "malaysia_states.topojson", "states"

# HIES survey year to map: None = the latest date in the file (2024 at time of writing).
HIES_DATE = None

# HIES district names that are spelled differently in the boundary file: "HIES name" -> "boundary name".
HIES_NAME_FIX = {
    "Pulau Pinang|S.P.Tengah": "Pulau Pinang|Seberang Perai Tengah",
    "Pulau Pinang|S.P.Utara": "Pulau Pinang|Seberang Perai Utara",
    "Pulau Pinang|S.P. Selatan": "Pulau Pinang|Seberang Perai Selatan",
    "Perak|Larut & Matang": "Perak|Larut Dan Matang",
    "Terengganu|Hulu": "Terengganu|Hulu Terengganu",
    "Sarawak|Lubok antu": "Sarawak|Lubok Antu",
}

# Areas drawn as a single district whose value comes from the state file when the
# district file has no row for them.
SINGLE_UNIT_STATES = ["Perlis", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya"]

# Dorling cartogram frame, in pixels. Must match width/height in map2 spec.
DORLING_W, DORLING_H, DORLING_RMAX = 560, 230, 70
# ------------------------------------------------------------------------


def read_csv(name):
    path = os.path.join(RAW, name)
    if not os.path.exists(path):
        raise SystemExit(f"Missing {path}. See README.md for where to download it.")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  read {name}: {len(rows):,} rows, columns = {list(rows[0].keys())}")
    return rows


def write_csv(name, rows, fields):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote data/{name}: {len(rows):,} rows ({os.path.getsize(path) / 1024:.0f} KB)")


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- geometry helpers
def topo_features(path, obj):
    """Decode a TopoJSON object into (properties, list of rings in lon/lat)."""
    if not os.path.exists(path):
        raise SystemExit(f"Missing boundary file {path}. Check TOPO_DIR and the file names in CONFIG.")
    t = json.load(open(path))
    if obj not in t.get("objects", {}):
        raise SystemExit(f'{os.path.basename(path)} has no object "{obj}". It has: {list(t.get("objects", {}))}. '
                         "Update the object name in CONFIG.")
    tr = t.get("transform")
    arcs = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for q in a:
            if tr:
                x += q[0]; y += q[1]
                pts.append((x * tr["scale"][0] + tr["translate"][0], y * tr["scale"][1] + tr["translate"][1]))
            else:
                pts.append(tuple(q))
        arcs.append(pts)

    def ring(r):
        out = []
        for i in r:
            out.extend(arcs[i] if i >= 0 else arcs[~i][::-1])
        return out

    feats = []
    for g in t["objects"][obj]["geometries"]:
        polys = [g["arcs"]] if g["type"] == "Polygon" else g.get("arcs", [])
        feats.append((g.get("properties", {}), [ring(r) for p in polys for r in p]))
    return feats


def centroid(rings):
    """Area-weighted centroid (shoelace formula) over all outer and inner rings."""
    A = cx = cy = 0.0
    for r in rings:
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            cross = x0 * y1 - x1 * y0
            A += cross; cx += (x0 + x1) * cross; cy += (y0 + y1) * cross
    if abs(A) < 1e-12:
        xs = [p[0] for r in rings for p in r]; ys = [p[1] for r in rings for p in r]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return cx / (3 * A), cy / (3 * A)


def dorling_layout(items, width=DORLING_W, height=DORLING_H, rmax=DORLING_RMAX, iterations=600):
    """items: list of dicts with lon, lat, weight. Returns the same dicts with
    x, y (pixels, y down) and r, area_px added. Circles start at their
    geographic position and are pushed apart until none overlap."""
    kx = math.cos(math.radians(3.5))  # equirectangular, standard parallel near Malaysia
    wmax = max(i["weight"] for i in items)
    for i in items:
        i["r"] = rmax * math.sqrt(i["weight"] / wmax)
        i["px"], i["py"] = i["lon"] * kx * 40, -i["lat"] * 40
    for _ in range(iterations):
        moved = False
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                p, q = items[a], items[b]
                dx, dy = q["px"] - p["px"], q["py"] - p["py"]
                d = math.hypot(dx, dy) or 1e-6
                overlap = p["r"] + q["r"] + 2 - d
                if overlap > 0:
                    mx, my = dx / d * overlap / 2, dy / d * overlap / 2
                    p["px"] -= mx; p["py"] -= my; q["px"] += mx; q["py"] += my
                    moved = True
        if not moved:
            break
    x0 = min(i["px"] - i["r"] for i in items); x1 = max(i["px"] + i["r"] for i in items)
    y0 = min(i["py"] - i["r"] for i in items); y1 = max(i["py"] + i["r"] for i in items)
    s = min((width - 8) / (x1 - x0), (height - 8) / (y1 - y0))
    for i in items:
        i["x"] = round((i["px"] - x0) * s + 4, 1)
        i["y"] = round((i["py"] - y0) * s + 4, 1)
        i["r"] = i["r"] * s
        i["area_px"] = round(math.pi * i["r"] ** 2, 1)
    return items


def waffle_cells(counts, order):
    """Largest-remainder rounding to exactly 100 cells, largest group first, Other last."""
    total = sum(counts.values())
    raw = {g: counts.get(g, 0) * 100 / total for g in order}
    cells = {g: int(v) for g, v in raw.items()}
    for g in sorted(order, key=lambda g: raw[g] - cells[g], reverse=True)[: 100 - sum(cells.values())]:
        cells[g] += 1
    seq = sorted([g for g in order if g != "Other"], key=lambda g: -cells[g]) + ["Other"]
    out, k = [], 0
    for g in seq:
        for _ in range(cells[g]):
            out.append({"cell": k, "theme_group": g}); k += 1
    return out


def year_runs(years, max_gap=GANTT_MAX_GAP):
    years = sorted(set(years))
    runs, start, prev = [], years[0], years[0]
    for y in years[1:]:
        if y - prev > max_gap + 1:
            runs.append((start, prev)); start = y
        prev = y
    runs.append((start, prev))
    return runs


# ---------------------------------------------------------------- steps
def lego():
    print("\n[1] LEGO data (Maven + Rebrickable)")
    maven = read_csv("lego_sets.csv")           # Maven Analytics LEGO Sets
    print("  Maven themeGroup values:", Counter(r["themeGroup"] for r in maven).most_common())

    if KEEP_CATEGORIES:
        print("  Maven category values:", Counter(r["category"] for r in maven).most_common())
        maven = [r for r in maven if r["category"] in KEEP_CATEGORIES]
        print(f"  kept {len(maven):,} sets in categories {KEEP_CATEGORIES}")
        print("  themeGroup values after filtering:", Counter(r["themeGroup"] for r in maven).most_common())

    sets_maven = []
    for r in maven:
        y = num(r["year"])
        if y is None:
            continue
        sets_maven.append({
            "set_id": r["set_id"], "name": r["name"], "year": int(y), "theme": r["theme"],
            "theme_group": GROUP_MAP.get(r["themeGroup"], "Other"),
            "pieces": num(r["pieces"]), "minifigs": num(r["minifigs"]),
            "min_age": num(r["agerange_min"]), "price_usd": num(r["US_retailPrice"]),
        })
    for f in ["pieces", "minifigs", "min_age", "price_usd"]:
        have = sum(1 for s in sets_maven if s[f] is not None)
        print(f"  {f}: {have:,} of {len(sets_maven):,} sets have a value")
    write_csv("sets_maven.csv", sets_maven,
              ["set_id", "year", "theme_group", "pieces", "minifigs", "min_age", "price_usd"])

    shares = Counter(s["theme_group"] for s in sets_maven)
    print("  theme group shares:", ", ".join(f"{g} {shares[g] / len(sets_maven):.1%}" for g in GROUPS))

    # waffle (chart 3)
    write_csv("waffle_cells.csv", waffle_cells(Counter(s["theme_group"] for s in sets_maven), GROUPS),
              ["cell", "theme_group"])

    # flagship sets (chart 9): print candidates so you can choose FLAGSHIP_SET_IDS yourself
    pool = [s for s in sets_maven if s["minifigs"]]
    print("  flagship candidates (most minifigures, with a price):")
    for s in sorted([s for s in pool if s["price_usd"]], key=lambda s: -s["minifigs"])[:15]:
        print(f'    {s["set_id"]:>10}  {s["year"]}  {s["theme"][:22]:<22} {s["name"][:38]:<38} '
              f'minifigs {s["minifigs"]:>4.0f}  USD {s["price_usd"]:>7.2f}  pieces {s["pieces"] or 0:>6.0f}')
    if FLAGSHIP_SET_IDS:
        flagship = [s for s in pool if s["set_id"] in FLAGSHIP_SET_IDS]
    else:
        flagship = sorted(pool, key=lambda s: -s["minifigs"])[:5]
    for s in flagship:
        s["set_name"] = f'{s["name"]} ({s["set_id"]})'
    write_csv("flagship_sets.csv", flagship, ["set_name", "theme_group", "minifigs", "price_usd"])

    # Rebrickable: theme tree -> root theme -> theme group (borrowed from Maven by theme name)
    themes = {t["id"]: t for t in read_csv("themes.csv")}
    def chain(tid):
        names = []
        while tid:
            t = themes.get(tid)
            if not t:
                break
            names.append(t["name"]); tid = t["parent_id"]
        return names  # leaf first, root last
    by_theme = defaultdict(Counter)
    for s in sets_maven:
        by_theme[s["theme"].lower()][s["theme_group"]] += 1
    theme_group = {k: c.most_common(1)[0][0] for k, c in by_theme.items()}

    rb, matched, dropped = [], 0, 0
    other_roots = Counter()
    for r in read_csv("sets.csv"):
        y, parts = num(r["year"]), num(r["num_parts"])
        if y is None:
            continue
        names = chain(r["theme_id"])
        root = names[-1] if names else ""
        if not (YEAR_MIN <= y <= YEAR_MAX):
            continue
        if (parts or 0) < REBRICKABLE_MIN_PARTS or root in REBRICKABLE_EXCLUDE:
            dropped += 1
            continue
        grp = REBRICKABLE_GROUP_OVERRIDES.get(root) or next(
            (theme_group[n.lower()] for n in names if n.lower() in theme_group), None)
        matched += grp is not None
        if grp is None:
            other_roots[root or "(no theme)"] += 1
        rb.append({"set_num": r["set_num"], "year": int(y), "num_parts": int(parts or 0),
                   "theme": names[-1] if names else "", "theme_path": " > ".join(reversed(names)),
                   "theme_group": grp or "Other"})
    print(f"  Rebrickable entries dropped (fewer than {REBRICKABLE_MIN_PARTS} part, or excluded themes): {dropped:,}")
    print(f"  Rebrickable sets given a theme group from Maven: {matched:,} of {len(rb):,} (rest -> Other)")
    print("  largest Rebrickable themes falling into Other:", other_roots.most_common(15))
    rshares = Counter(s["theme_group"] for s in rb)
    print("  Rebrickable theme group shares:", ", ".join(f"{g} {rshares[g] / len(rb):.1%}" for g in GROUPS))
    write_csv("sets_rebrickable.csv", rb, ["set_num", "year", "num_parts", "theme", "theme_group"])

    # Gantt intervals (chart 4)
    rows = []
    for th in GANTT_THEMES:
        hits = [s for s in rb if th.lower() in [p.strip().lower() for p in s["theme_path"].split(">")]]
        if not hits:
            print(f"  ! Gantt theme not found in Rebrickable: {th}")
            continue
        grp = Counter(s["theme_group"] for s in hits).most_common(1)[0][0]
        runs = [(a, b) for a, b in year_runs([s["year"] for s in hits])
                if sum(1 for s in hits if a <= s["year"] <= b) >= GANTT_MIN_RUN_SETS]
        if not runs:
            continue
        for a, b in runs:
            rows.append({"theme": th, "theme_group": grp, "start": a, "end": b, "first_start": runs[0][0],
                         "sets": sum(1 for s in hits if a <= s["year"] <= b)})
    write_csv("theme_intervals.csv", rows, ["theme", "theme_group", "start", "end", "first_start", "sets"])
    return flagship


def malaysia(flagship):
    print("\n[2] Malaysian data (OpenDOSM)")
    districts = topo_features(os.path.join(PROJECT, TOPO_DIR, DISTRICTS_FILE), DISTRICTS_OBJECT)
    cent = {f'{p["state"]}|{p["district"]}': centroid(r) for p, r in districts}

    hies = read_csv("hies_district.csv")
    date = HIES_DATE or max(r["date"] for r in hies)
    rows, no_shape = [], []
    for r in hies:
        if r["date"] != date:
            continue
        key = HIES_NAME_FIX.get(f'{r["state"]}|{r["district"]}', f'{r["state"]}|{r["district"]}')
        if key not in cent:
            no_shape.append(key)
            continue
        st, dist = key.split("|", 1)
        lon, lat = cent[key]
        rows.append({"key": key, "state": st, "district": dist,
                     "expenditure_mean": r["expenditure_mean"], "income_mean": r["income_mean"],
                     "lon": round(lon, 4), "lat": round(lat, 4), "source": "district"})

    # single-unit areas: fill from the state file if the district file has no row
    hs_rows = read_csv("hies_state.csv")
    have = {r["key"] for r in rows}
    for st in SINGLE_UNIT_STATES:
        shape_keys = [k for k in cent if k.split("|", 1)[0] == st]
        srow = next((r for r in hs_rows if r["state"] == st and r["date"] == date), None)
        for k in shape_keys:
            if k in have or srow is None:
                continue
            lon, lat = cent[k]
            rows.append({"key": k, "state": st, "district": k.split("|", 1)[1],
                         "expenditure_mean": srow["expenditure_mean"], "income_mean": srow["income_mean"],
                         "lon": round(lon, 4), "lat": round(lat, 4), "source": "state"})
            print(f"  filled {k} from the state file")

    print(f"  HIES {date}: {len(rows)} districts matched to boundaries")
    print(f"  HIES districts with no boundary shape (cannot be drawn; mention on the page): {no_shape or 'none'}")
    missing = sorted(set(cent) - {r["key"] for r in rows})
    print(f"  boundary districts still without data (shown grey): {missing or 'none'}")
    write_csv("hies_district.csv", rows, ["key", "state", "district", "expenditure_mean", "income_mean", "lon", "lat", "source"])

    # Dorling cartogram inputs (map 2)
    pop = defaultdict(float)
    prows = read_csv("population_district.csv")
    platest = max(r["date"] for r in prows)
    for r in prows:
        if r["date"] == platest and r["sex"] == "both" and r["age"] == "overall" and r["ethnicity"] == "overall":
            pop[r["state"]] += num(r["population"]) or 0
    spend = {r["state"]: num(r["expenditure_mean"]) for r in hs_rows if r["date"] == date}

    price_usd = FLAGSHIP_PRICE_USD
    if price_usd is None:
        prices = sorted(s["price_usd"] for s in flagship if s["price_usd"])
        price_usd = prices[len(prices) // 2] if prices else 100.0
    price_rm = price_usd * USD_TO_RM
    print(f"  flagship price used for map 2: USD {price_usd:.2f} = RM {price_rm:.2f}")

    states = topo_features(os.path.join(PROJECT, TOPO_DIR, STATES_FILE), STATES_OBJECT)
    items = []
    for p, r in states:
        st = p["state"]
        if st not in pop or st not in spend:
            print(f"  ! state missing population or spending: {st}")
            continue
        lon, lat = centroid(r)
        items.append({"state": st, "label": st.replace("W.P. ", ""), "lon": lon, "lat": lat,
                      "weight": pop[st], "population_k": round(pop[st], 1),
                      "expenditure_mean": spend[st], "price_rm": round(price_rm, 2),
                      "share_pct": round(price_rm / spend[st] * 100, 1)})
    dorling_layout(items)
    write_csv("dorling_states.csv", items,
              ["state", "label", "x", "y", "area_px", "population_k", "expenditure_mean", "price_rm", "share_pct"])


if __name__ == "__main__":
    flagship = lego()
    malaysia(flagship)
    print("\nDone. toy_imports.csv (map 3) is filled in by hand from OEC; see README.md.")