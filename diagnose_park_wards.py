import json
import re
import sqlite3
from collections import Counter

from shapely.geometry import Polygon

t = open(
    "/home/mesh/Pune-Climate-ML/ml_pipeline/reference/pune_parks.kml",
    encoding="utf-8",
    errors="replace",
).read()
pms = re.findall(r"<Placemark.*?</Placemark>", t, re.S)


def ring_of(pm):
    rings = []
    for rm in re.finditer(r"<LinearRing>(.*?)</LinearRing>", pm, re.S):
        co = [
            (float(a), float(b))
            for a, b in re.findall(r"(-?[\d.]+),(-?[\d.]+)", rm.group(1))
        ]
        if len(co) >= 3:
            rings.append(co)
    return max(rings, key=len) if rings else None


def name_of(pm):
    m = re.search(r'<SimpleData name="structure_">(.*?)</SimpleData>', pm, re.S)
    return m.group(1).strip() if m else None


conn = sqlite3.connect("/home/mesh/Pune-Climate-ML/ml_pipeline/data/reference_layers.sqlite")
W = {}
for wn, rj in conn.execute("SELECT ward_no, ring_json FROM wards"):
    p = Polygon(json.loads(rj))
    if not p.is_valid:
        p = p.buffer(0)
    W[wn] = p

names = [name_of(p) for p in pms]
dups = [n for n, c in Counter(names).items() if c > 1]
print("duplicate park names:", len(dups))
for d in dups:
    print("   ", d)

for target_name in ("Nana Nani Udyan", "Hirbai Udyan"):
    print("\n=== %s ===" % target_name)
    for pm in pms:
        if name_of(pm) != target_name:
            continue
        r = ring_of(pm)
        raw = Polygon(r)
        poly = raw if raw.is_valid else raw.buffer(0)
        print("  valid:", raw.is_valid, " verts:", len(r))
        print("  bounds lon/lat:", [round(v, 5) for v in poly.bounds])
        hits = [w for w, wp in W.items() if wp.intersects(poly)]
        print("  wards intersecting:", hits)
        for w in hits:
            frac = poly.intersection(W[w]).area / poly.area if poly.area else 0
            print("     ward %2d overlap %.4f" % (w, frac))
        db = conn.execute(
            "SELECT ward_no, centroid_lon, centroid_lat, prabhag_name, locality "
            "FROM parks WHERE name = ?",
            (target_name,),
        ).fetchall()
        print("  db:", db)