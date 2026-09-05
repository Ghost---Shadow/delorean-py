"""Scoring two extracted images against each other.

Silhouette IoU is the gate; everything else is a diagnostic.

Why not gate on PSNR/MSE, which is what people reach for first: edge maps are
sparse and binary. A uniform two-pixel offset — a shape that is *correct*, just
framed slightly differently — destroys PSNR, while PSNR saturates as soon as
edges are merely near one another. It is not a shape metric. Chamfer distance
and boundary F-score say the useful thing instead, in units you can act on:
"your edges are 4 px out on average" and "you are missing 20% of the reference
edges and inventing 10% of your own".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .edges import Extracted


@dataclass
class Scores:
    silhouette_iou: float
    silhouette_dice: float
    chamfer_px: float
    chamfer_normalised: float
    boundary_f1: float
    boundary_precision: float
    boundary_recall: float
    edge_psnr_db: float
    edge_mse: float
    width: int
    height: int

    def as_dict(self) -> dict:
        return {k: (round(v, 5) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}

    def summary(self) -> str:
        return (f"IoU {self.silhouette_iou:.4f}  "
                f"chamfer {self.chamfer_px:5.2f}px  "
                f"F1 {self.boundary_f1:.3f} "
                f"(P {self.boundary_precision:.3f} / R {self.boundary_recall:.3f})  "
                f"PSNR {self.edge_psnr_db:5.2f}dB")


def _align(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if a.shape == b.shape:
        return a, b
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    return (cv2.resize(a, (w, h), interpolation=cv2.INTER_NEAREST),
            cv2.resize(b, (w, h), interpolation=cv2.INTER_NEAREST))


def silhouette_iou(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a, b = _align(a, b)
    pa, pb = a > 127, b > 127
    inter = float(np.count_nonzero(pa & pb))
    union = float(np.count_nonzero(pa | pb))
    total = float(np.count_nonzero(pa) + np.count_nonzero(pb))
    iou = inter / union if union else 0.0
    dice = 2.0 * inter / total if total else 0.0
    return iou, dice


def chamfer(a_edge: np.ndarray, b_edge: np.ndarray) -> tuple[float, float]:
    """Symmetric mean distance, in pixels, between two edge sets.

    Distance-transform the reference, sample the render's edges into it, and
    vice versa. A number you can reason about: "8 px out" means something,
    where "PSNR 12 dB" does not.
    """
    a_edge, b_edge = _align(a_edge, b_edge)
    pa, pb = a_edge > 127, b_edge > 127
    if not pa.any() or not pb.any():
        return float("inf"), float("inf")

    dt_a = cv2.distanceTransform((~pa).astype(np.uint8), cv2.DIST_L2, 3)
    dt_b = cv2.distanceTransform((~pb).astype(np.uint8), cv2.DIST_L2, 3)
    d = 0.5 * (float(dt_a[pb].mean()) + float(dt_b[pa].mean()))
    diagonal = float(np.hypot(*a_edge.shape))
    return d, d / diagonal


def boundary_f(a_edge: np.ndarray, b_edge: np.ndarray,
               tolerance: int = 3) -> tuple[float, float, float]:
    """Precision/recall on edges with a slack radius (BSDS style).

    Precision says how much of what the model drew actually exists on the real
    car; recall says how much of the real car the model drew. Separating them
    matters: a smooth blob and a car covered in invented panel lines both score
    badly on F1, but for opposite reasons.
    """
    a_edge, b_edge = _align(a_edge, b_edge)
    pa, pb = a_edge > 127, b_edge > 127
    if not pa.any() or not pb.any():
        return 0.0, 0.0, 0.0

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                  (2 * tolerance + 1, 2 * tolerance + 1))
    a_near = cv2.dilate(pa.astype(np.uint8), k) > 0
    b_near = cv2.dilate(pb.astype(np.uint8), k) > 0

    precision = float(np.count_nonzero(pb & a_near)) / float(np.count_nonzero(pb))
    recall = float(np.count_nonzero(pa & b_near)) / float(np.count_nonzero(pa))
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return f1, precision, recall


def edge_psnr(a_edge: np.ndarray, b_edge: np.ndarray) -> tuple[float, float]:
    """Reported for familiarity. Not a gate — see the module docstring."""
    a_edge, b_edge = _align(a_edge, b_edge)
    diff = a_edge.astype(np.float64) - b_edge.astype(np.float64)
    mse = float(np.mean(diff ** 2))
    if mse <= 1e-12:
        return 99.0, 0.0
    return float(10.0 * np.log10((255.0 ** 2) / mse)), mse


def compare(reference: Extracted, render: Extracted,
            tolerance: int = 3) -> Scores:
    iou, dice = silhouette_iou(reference.mask, render.mask)
    ch_px, ch_norm = chamfer(reference.edge, render.edge)
    f1, precision, recall = boundary_f(reference.edge, render.edge, tolerance)
    psnr, mse = edge_psnr(reference.edge, render.edge)
    h, w = _align(reference.mask, render.mask)[0].shape
    return Scores(
        silhouette_iou=iou, silhouette_dice=dice,
        chamfer_px=ch_px, chamfer_normalised=ch_norm,
        boundary_f1=f1, boundary_precision=precision, boundary_recall=recall,
        edge_psnr_db=psnr, edge_mse=mse, width=w, height=h)


def overlay(reference: Extracted, render: Extracted) -> np.ndarray:
    """A picture of the disagreement: reference in red, render in green."""
    a, b = _align(reference.edge, render.edge)
    ma, mb = _align(reference.mask, render.mask)
    canvas = np.zeros((*a.shape, 3), np.uint8)
    canvas[..., 2] = np.maximum(a, (ma > 127) * 40)      # reference -> red
    canvas[..., 1] = np.maximum(b, (mb > 127) * 40)      # render    -> green
    return canvas
