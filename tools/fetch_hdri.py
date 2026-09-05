"""Download HDRI environment maps from Poly Haven.

CLAUDE.md says the repo ships no external assets, and that still holds: the
HDRI files land in `assets/hdri/`, which is gitignored. What is committed is
this script and the shortlist below, so a clean clone can reproduce the same
environments with one command. The build falls back to the procedural sky when
no file is present, so nothing here is required to get a render.

Poly Haven assets are CC0 — public domain, commercial use fine, redistribution
fine, attribution not required (https://polyhaven.com/license). Credit is
recorded in `assets/hdri/CREDITS.md` anyway, because it is cheap and decent.

    python tools/fetch_hdri.py                 # the shortlist, 2k
    python tools/fetch_hdri.py --res 4k
    python tools/fetch_hdri.py --list          # what is available
    python tools/fetch_hdri.py --search garage
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "hdri"
API = "https://api.polyhaven.com"
UA = {"User-Agent": "delorean-py/0.1 (+https://github.com/Ghost---Shadow/delorean-py)"}

#: Chosen for bare stainless steel, which shows whatever you put around it.
#: A car needs an environment with large, clearly shaped bright sources; an
#: even grey dome gives a flat, dead-looking metal.
SHORTLIST = {
    "brown_photostudio_02": "studio - large softboxes, the default car-render look",
    "autoshop_01": "garage - strip lights overhead, thematically right for a DMC",
    "empty_warehouse_01": "industrial shed, close to the rear-quarter reference",
    "evening_road_01": "dusk street, closest to how the references were shot",
    "kloppenheim_06": "open sky with a sun, for hard outdoor speculars",
}


def api(path: str):
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh)


def download(slug: str, res: str = "2k", fmt: str = "hdr") -> Path | None:
    files = api(f"/files/{slug}")
    try:
        meta = files["hdri"][res][fmt]
    except KeyError:
        print(f"  {slug}: no {res} {fmt}")
        return None

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"{slug}_{res}.{fmt}"
    if dst.exists() and dst.stat().st_size == meta["size"]:
        print(f"  {slug:<24} already present ({meta['size'] / 1e6:.1f} MB)")
        return dst

    print(f"  {slug:<24} {meta['size'] / 1e6:5.1f} MB ...", end="", flush=True)
    req = urllib.request.Request(meta["url"], headers=UA)
    with urllib.request.urlopen(req, timeout=600) as src, open(dst, "wb") as out:
        while chunk := src.read(1 << 20):
            out.write(chunk)
    print(" done")
    return dst


def write_credits(slugs: list[str]) -> None:
    lines = ["# HDRI credits", "",
             "Environment maps from [Poly Haven](https://polyhaven.com), released",
             "under [CC0](https://polyhaven.com/license) — public domain.",
             "Attribution is not required; recorded here as a courtesy.", ""]
    for slug in slugs:
        try:
            info = api(f"/info/{slug}")
        except Exception:
            continue
        authors = ", ".join(info.get("authors", {})) or "Poly Haven"
        lines.append(f"- **{info.get('name', slug)}** by {authors} — "
                     f"https://polyhaven.com/a/{slug}")
    (OUT / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="2k", choices=("1k", "2k", "4k", "8k"))
    ap.add_argument("--format", default="hdr", choices=("hdr", "exr"))
    ap.add_argument("--only", default=None, help="one slug from the shortlist")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--search", default=None)
    args = ap.parse_args()

    if args.search:
        assets = api("/assets?t=hdris")
        for slug in sorted(a for a in assets if args.search.lower() in a.lower()):
            print(f"  {slug:<36} {assets[slug].get('name', '')}")
        return

    if args.list:
        for slug, why in SHORTLIST.items():
            print(f"  {slug:<24} {why}")
        return

    slugs = [args.only] if args.only else list(SHORTLIST)
    print(f"\n  downloading {len(slugs)} HDRI(s) at {args.res} -> "
          f"{OUT.relative_to(ROOT)}")
    got = [s for s in slugs if download(s, args.res, args.format)]
    if got:
        write_credits(got)
        print(f"  credits -> {(OUT / 'CREDITS.md').relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
