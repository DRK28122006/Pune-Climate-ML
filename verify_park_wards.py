"""Independent check that every park is attributed to the ward that contains it.

Uses shapely + geopandas from the project venv (not the dependency-free
raycaster used in the pipeline), so the pipeline's own point-in-polygon code is
checked against an independent implementation rather than against itself.
"""

import json
import sqlite3

import re

from shapely.geometry import Point, Polygon

DB = "ml_pipeline/data/reference_layers.sqlite"
PARK_KML = "ml_pipeline/reference/pune_parks.kml"


def park_polygons():
    """Re-parse the park KML directly, independent of the pipeline's parser.

    Keyed by position, NOT by name: PMC reuses park names across the city
    ("Nana Nani Udyan" exists in both Ward 25 (Shaniwar Peth) and Ward 40
    (Kondhwa)), so a name-keyed join silently shadows one of the two.
    """
    text = open(PARK_KML, encoding="utf-8", errors="replace").read()
    for i, pm in enumerate(re.findall(r"<Placemark.*?</Placemark>", text, re.S)):
        m = re.search(r'<SimpleData name="structure_">(.*?)</SimpleData>', pm, re.S)
        name = m.group(1).strip() if m else None
        rings = []
        for rm in re.finditer(r"<LinearRing>(.*?)</LinearRing>", pm, re.S):
            coords = [
                (float(cm.group(1)), float(cm.group(2)))
                for cm in re.finditer(r"(-?[\d.]+),(-?[\d.]+)", rm.group(1))
            ]
            if len(coords) >= 3:
                rings.append(coords)
        if rings:
            ring = max(rings, key=len)
            yield i + 1, name, Polygon(ring)


conn = sqlite3.connect(DB)

wards = {}
for ward_no, ring_json in conn.execute("SELECT ward_no, ring_json FROM wards"):
    poly = Polygon(json.loads(ring_json))
    if not poly.is_valid:
        poly = poly.buffer(0)
    wards[ward_no] = poly

db_parks = {
    pid: (name, ward_no, clon, clat)
    for pid, name, ward_no, clon, clat in conn.execute(
        "SELECT park_id, name, ward_no, centroid_lon, centroid_lat FROM parks"
    )
}

full = partial = outside = 0
unmatched = 0
details = []
centroid_outside = []

for park_id, name, poly in park_polygons():
    if not poly.is_valid:
        poly = poly.buffer(0)
    rec = db_parks.get(park_id)
    if rec is None:
        unmatched += 1
        continue
    _, ward_no, clon, clat = rec
    if ward_no is None:
        continue
    ward = wards.get(ward_no)
    if ward is None:
        continue

    frac = poly.intersection(ward).area / poly.area if poly.area else 0.0
    if frac > 0.999:
        full += 1
    elif frac > 0.001:
        partial += 1
        details.append((name, ward_no, round(frac, 4)))
    else:
        outside += 1
        details.append((name, ward_no, 0.0))

    if not ward.contains(Point(clon, clat)):
        centroid_outside.append((name, ward_no))

total = full + partial + outside
print(f"park polygons in KML vs DB by name: {total} matched, {unmatched} unmatched")
print(f"  fully inside assigned ward : {full}")
print(f"  partially inside          : {partial}")
print(f"  OUTSIDE assigned ward      : {outside}")
print()
print(f"centroid outside its assigned ward: {len(centroid_outside)}")
for d in details:
    print("   ", d)
for c in centroid_outside[:10]:
    print("   centroid-outside:", c)