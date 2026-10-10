"""Build a static visual map of every factor in every cell.

Reads ml_pipeline/data/epoch_cube.json, recomputes per-cell flood / heat /
green with the LIVE scorer (same functions assess uses), and writes a single
self-contained Leaflet page (CDN tiles) to ml_pipeline/ui/index.html.

Carbon is per-BOQ, not spatial: shown as a constant note, not a layer.

Usage:
    .venv/bin/python ml_pipeline/ui/build_map.py
    # then open ml_pipeline/ui/index.html in a browser
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ml_pipeline.core.scoring import (
    area_weighted_cn,
    compute_flood,
    compute_green,
    compute_heat,
)

HERE = os.path.dirname(os.path.abspath(__file__))
CUBE = os.path.join(HERE, "..", "data", "epoch_cube.json")
REGION = os.path.join(HERE, "..", "config", "regions", "pune.json")
OUT = os.path.join(HERE, "index.html")

LAYERS = ["flood", "heat", "green", "built", "vegetation", "night_delta", "elevation"]


def main():
    cube = json.load(open(CUBE))
    region = json.load(open(REGION))
    hyd = region.get("hydrology", {})
    therm = region.get("thermal", {})
    cn_table = hyd.get("cn_table", {})
    storm = hyd.get("design_storm_mm", 150.0)
    night_ref = therm.get("night_reference_c")
    night_span = therm.get("night_uhi_max_delta_c", 5.0)

    cells = []
    for cid, r in cube["cells"].items():
        if not r:
            continue
        lon, lat = map(float, cid.split("_"))
        built = r.get("built_pct", 0) * 100
        veg = r.get("vegetation_pct", 0) * 100
        water = r.get("water_pct", 0) * 100
        bare = (r.get("bare_season_pct", r.get("bare_pct", 0)) or 0) * 100
        nm = r.get("lst_night_mean_c")

        flood = compute_flood(built, veg, water, storm, cn_table, bare_pct=bare)
        heat = compute_heat(nm, night_ref, night_span) if nm is not None else {"score": None}
        green = compute_green(veg, 0.0)  # satellite-only context (no site canopy)
        cells.append({
            "id": cid, "lon": lon, "lat": lat,
            "flood": round(flood["score"], 1),
            "cn": round(flood["curve_number"], 1),
            "runoff": round(flood["runoff_mm"], 1),
            "heat": round(heat["score"], 1) if heat["score"] is not None else None,
            "green": round(green["score"], 1),
            "built": round(built, 1),
            "vegetation": round(veg, 1),
            "night_delta": round(nm - night_ref, 2) if nm is not None else None,
            "night_mean": round(nm, 1) if nm is not None else None,
            "elevation": round(r.get("elevation_m", 0), 0),
        })
    scored = sum(1 for c in cells if c["heat"] is not None)
    print(f"cells: {len(cells)}, heat scored: {scored}")

    data_json = json.dumps(cells, separators=(",", ":"))
    layers_json = json.dumps(LAYERS)

    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Dishadharti - PMC factor map (864 cells)</title>
<link rel="stylesheet" href="leaflet.css">
<script src="leaflet.js"></script>
<style>
body{margin:0;font-family:system-ui,sans-serif}
#map{height:100vh}
#panel{position:absolute;top:10px;left:50px;z-index:1000;background:#fff;
 padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);max-width:330px}
#panel h3{margin:0 0 6px;font-size:15px}
#panel select{width:100%;margin:4px 0}
#legend{margin-top:6px;font-size:12px}
#stats{font-size:12px;color:#333;margin-top:6px}
.bar{display:inline-block;height:10px}
</style></head><body>
<div id="map"></div>
<div id="panel">
<h3>Dishadharti - PMC 864 cells</h3>
<div>High score = worse. Carbon is per-BOQ (not spatial).</div>
<select id="layer"></select>
<div id="legend"></div>
<div id="stats"></div>
</div>
<script>
const CELLS = __DATA__;
const LAYERS = __LAYERS__;
const map = L.map('map').setView([18.5036, 73.875], 11);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
 {maxZoom:19, attribution:'OSM'}).addTo(map);
let grid = null;
function color(v){
 if(v==null) return '#999999';
 // green -> yellow -> red across 0..100
 const h = Math.max(0, 120 - v*1.2);
 return 'hsl('+h+',85%,45%)';
}
const LABELS = {flood:'Flood (runoff vs 150mm storm)', heat:'Heat (night LST vs rural 17.96)',
 green:'Green cover (satellite only)', built:'Built-up %', vegetation:'Vegetation %',
 night_delta:'Night delta C (site minus rural)', elevation:'Elevation m'};
const MAXV = {elevation: 1031};
function draw(layer){
 if(grid) map.removeLayer(grid);
 const max = MAXV[layer] || 100;
 const scale = v => layer==='elevation' ? (v/max*100) : (layer==='night_delta' ? Math.min(100, Math.max(0,(v+2)/8*100)) : v);
 grid = L.layerGroup(CELLS.map(c=>{
  const v = c[layer];
  const half = 0.0045;
  const rect = L.rectangle([[c.lat-half,c.lon-half],[c.lat+half,c.lon+half]],
   {color:color(scale(v)), weight:0.4, fillColor:color(scale(v)), fillOpacity:0.65});
  rect.bindPopup('<b>cell '+c.id+'</b><br>flood '+c.flood+' (CN '+c.cn+', runoff '+c.runoff+'mm)'+
   '<br>heat '+(c.heat==null?'n/a':c.heat)+' (night '+c.night_mean+'C, delta '+c.night_delta+')'+
   '<br>green '+c.green+'<br>built '+c.built+'% veg '+c.vegetation+'% elev '+c.elevation+'m');
  return rect;
 })).addTo(map);
 const vals = CELLS.map(c=>c[layer]).filter(v=>v!=null);
 const s = vals.length? ('n='+vals.length+' min='+Math.min(...vals).toFixed(1)+
  ' med='+vals.slice().sort((a,b)=>a-b)[Math.floor(vals.length/2)].toFixed(1)+
  ' max='+Math.max(...vals).toFixed(1)) : 'no data';
 document.getElementById('stats').textContent = LABELS[layer]+' - '+s;
 document.getElementById('legend').innerHTML =
  '<span class="bar" style="width:120px;background:linear-gradient(90deg,hsl(120,85%,45%),hsl(60,85%,45%),hsl(0,85%,45%))"></span> low - high';
}
const sel = document.getElementById('layer');
LAYERS.forEach(l=>{const o=document.createElement('option');o.value=l;
 o.textContent=LABELS[l]||l;sel.appendChild(o);});
sel.onchange = ()=>draw(sel.value);
draw('heat');
</script></body></html>"""
    html = html.replace("__DATA__", data_json).replace("__LAYERS__", layers_json)
    open(OUT, "w").write(html)
    print(f"wrote {OUT} ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()
