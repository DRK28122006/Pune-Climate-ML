"""Download the remaining PMC Tree Census CSV parts.

ptc_part1.csv is a geographic BLOCK, not a random sample: it holds 249,999 of
4,090,000 trees and leaves 15 of 41 wards completely empty. This fetches the
remaining parts so ward-level tree figures stop meaning "not loaded".

Usage:
    .venv/bin/python ml_pipeline/data/fetch_census_parts.py --list
    .venv/bin/python ml_pipeline/data/fetch_census_parts.py --parts 2 3 4
    .venv/bin/python ml_pipeline/data/fetch_census_parts.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CENSUS_DIR = REPO / "ml_pipeline" / "data" / "census"
PACKAGE = "f00d83b8-c70f-4fff-9ac7-9a6ab4255edf"
BASE = f"https://data.opencity.in/api/3/action/package_show?id={PACKAGE}"


def package_show() -> Dict[str, Any]:
    req = urllib.request.Request(BASE, headers={"User-Agent": "dishadharti/1.0"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.loads(fh.read().decode("utf-8"))["result"]


def find_resources(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The census CSVs, in part order.

    The resources are named "Tree Census - Part N", NOT "ptc_partN.csv" -- the
    file the repo already has was renamed locally after download. Matching on
    "ptc" therefore finds nothing, which is how the first version of this script
    reported "0 resources" against a package that plainly contains 17.
    """
    out: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("format", "").upper() in ("CSV", "XLSX") and node.get("url"):
                name = node.get("name", "")
                url = node["url"]
                low = f"{name} {url}".lower()
                if "tree census" in low or "ptc" in low:
                    out.append({"name": name, "url": url, "format": node.get("format")})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(result.get("resources", []))

    # Deduplicate by URL, preserving order.
    seen = set()
    uniq = []
    for r in out:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        uniq.append(r)

    def part_of(r: Dict[str, Any]) -> int:
        digits = ""
        for ch in r.get("name", ""):
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if digits:
            return int(digits)
        # Fall back to the resource UUID, so ordering is at least stable.
        tail = r["url"].rstrip("/").split("/")[-1]
        return 999 if not tail else 1000

    return sorted(uniq, key=part_of)


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  already have {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
        return True
    print(f"  GET {dest.name}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dishadharti/1.0"})
        with urllib.request.urlopen(req, timeout=300) as fh:
            data = fh.read()
        dest.write_bytes(data)
        print(f"    -> {len(data)/1e6:.1f} MB")
        return True
    except urllib.error.HTTPError as exc:
        print(f"    HTTP {exc.code}: {exc.reason}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR {type(exc).__name__}: {str(exc)[:120]}")
        return False


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_census_parts")
    ap.add_argument("--list", action="store_true", help="list available parts")
    ap.add_argument("--parts", nargs="*", type=int, help="part numbers to download")
    ap.add_argument("--all", action="store_true", help="download every part")
    args = ap.parse_args(argv)

    result = package_show()
    resources = find_resources(result)
    print(f"PMC census package: {result.get('title')}")
    print(f"resources matching 'ptc': {len(resources)}\n")

    if args.list or not (args.all or args.parts):
        for i, r in enumerate(resources, start=1):
            print(f"  {i:>2}. {r['name']}")
            print(f"      {r['url']}")
        if not (args.all or args.parts):
            print("\n(re-run with --all or --parts N to download)")
            return 0

    targets = resources
    if args.parts:
        targets = [r for i, r in enumerate(resources, start=1) if i in set(args.parts)]

    print(f"\ndownloading {len(targets)} part(s) into {CENSUS_DIR}")
    ok = 0
    for r in targets:
        name = Path(r["url"].split("?")[0]).name
        if download(r["url"], CENSUS_DIR / name):
            ok += 1
    print(f"\ndownloaded {ok}/{len(targets)}")
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())