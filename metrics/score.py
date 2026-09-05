"""Score the current build against the reference photographs.

Runs in system Python, outside Blender.

    python -m metrics.score
    python -m metrics.score --only gravel --write-baseline

Expects, per scored reference:
    references/<stem>.<ext>                 the photograph
    references/masks/<stem>.png             its car mask
    references/cameras/<stem>.camera.json   the solved camera
    renders/metrics/<stem>.png              a clay render from that camera

Produce the render with:
    blender -b -P metrics/render_solved.py -- --reference <stem>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from .compare import compare, overlay
from .edges import extract

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"
MASKS = REFS / "masks"
CAMERAS = REFS / "cameras"
RENDERS = ROOT / "renders" / "metrics"
OUT = ROOT / "metrics" / "out"
BASELINE = ROOT / "metrics" / "baseline.json"

#: measured, not invented. Set from what an honest build actually scores, then
#: ratcheted upward as the model improves.
GATE_IOU = 0.70


def scored_references() -> list[dict]:
    spec = json.loads((REFS / "masks.json").read_text())
    return [m for m in spec["masks"] if m.get("scored", False)]


def find_reference(stem: str) -> Path:
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = REFS / (stem + ext)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no reference image for {stem}")


def score_one(stem: str, width: int = 900, tolerance: int = 3) -> dict | None:
    render = RENDERS / (stem + ".png")
    mask = MASKS / (stem + ".png")
    if not render.exists():
        print(f"  {stem:<42} no render yet "
              f"(blender -b -P metrics/render_solved.py -- --reference {stem})")
        return None
    if not mask.exists():
        print(f"  {stem:<42} no mask (run tools/make_masks.py)")
        return None

    reference = extract(find_reference(stem), mask_path=mask, width=width)
    rendered = extract(render, width=width, from_backdrop=True)
    scores = compare(reference, rendered, tolerance=tolerance)

    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / f"{stem}.overlay.png"), overlay(reference, rendered))
    cv2.imwrite(str(OUT / f"{stem}.ref-edges.png"), reference.edge)
    cv2.imwrite(str(OUT / f"{stem}.render-edges.png"), rendered.edge)

    solved = CAMERAS / (stem + ".camera.json")
    record = scores.as_dict()
    if solved.exists():
        record["camera"] = json.loads(solved.read_text())
    return record


def main() -> int:
    ap = argparse.ArgumentParser(prog="metrics.score")
    ap.add_argument("--only", default=None)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--tolerance", type=int, default=3,
                    help="boundary F-score slack, in pixels")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    print("\n  fidelity against reference photographs")
    print("  " + "-" * 76)

    results: dict[str, dict] = {}
    for entry in scored_references():
        stem = Path(entry["src"]).stem
        if args.only and args.only.lower() not in stem.lower():
            continue
        record = score_one(stem, args.width, args.tolerance)
        if record is None:
            continue
        results[stem] = record
        gate = "PASS" if record["silhouette_iou"] >= GATE_IOU else "below gate"
        print(f"  {stem}")
        print(f"      IoU {record['silhouette_iou']:.4f} ({gate}, gate {GATE_IOU:.2f})"
              f"   dice {record['silhouette_dice']:.4f}")
        print(f"      chamfer {record['chamfer_px']:6.2f} px"
              f"   boundary F1 {record['boundary_f1']:.3f}"
              f"  (P {record['boundary_precision']:.3f} /"
              f" R {record['boundary_recall']:.3f})")
        print(f"      edge PSNR {record['edge_psnr_db']:5.2f} dB"
              f"   [reported, not a gate]")

    print("  " + "-" * 76)
    if not results:
        print("  nothing scored\n")
        return 0

    mean_iou = sum(r["silhouette_iou"] for r in results.values()) / len(results)
    print(f"  mean silhouette IoU {mean_iou:.4f} over {len(results)} view(s)")
    print(f"  overlays -> {OUT.relative_to(ROOT)}\n")

    if args.write_baseline:
        BASELINE.write_text(json.dumps(
            {"gate_iou": GATE_IOU, "views": results}, indent=2), encoding="utf-8")
        print(f"  baseline written -> {BASELINE.relative_to(ROOT)}\n")

    return 0 if mean_iou >= GATE_IOU else 1


if __name__ == "__main__":
    raise SystemExit(main())
