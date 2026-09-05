"""Edge and silhouette extraction.

Both the render and the reference get reduced to two things: a binary
silhouette mask, and a binary edge map. Everything downstream scores those.

Backgrounds are the reason this is not trivial. A reference photograph has
foliage, gravel, a rusty wall — Canny fires on all of it, and an unmasked edge
metric mostly measures trees. So a reference is only scored if a car mask sits
beside it; renders get their mask for free because the backdrop is a known flat
colour.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Extracted:
    """A picture reduced to the two things worth comparing."""

    mask: np.ndarray        # uint8 {0, 255}, the car's silhouette
    edge: np.ndarray        # uint8 {0, 255}, edges inside the mask
    gray: np.ndarray        # uint8, for reference
    source: str = ""

    @property
    def size(self) -> tuple[int, int]:
        return self.mask.shape[1], self.mask.shape[0]


def load_gray(path: str | Path, width: int | None = None) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    if width and img.shape[1] != width:
        h = int(round(img.shape[0] * width / img.shape[1]))
        img = cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep only the biggest blob — drops speckle and stray background."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8)
    if n <= 1:
        return mask
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == biggest, 255, 0).astype(np.uint8)


def clean_mask(mask: np.ndarray, close: int = 7) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    filled = mask.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    return largest_component(filled)


def mask_from_backdrop(path: str | Path, width: int | None = None,
                       tolerance: int = 46) -> np.ndarray:
    """Silhouette of a render, taken from its known flat backdrop colour.

    The backdrop colour is sampled from the image corners rather than assumed,
    so this works for the blueprint-blue part previews and the grey studio
    alike.
    """
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    if width and img.shape[1] != width:
        h = int(round(img.shape[0] * width / img.shape[1]))
        img = cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)

    h, w = img.shape[:2]
    p = max(4, min(h, w) // 40)
    corners = np.concatenate([
        img[:p, :p].reshape(-1, 3), img[:p, -p:].reshape(-1, 3),
        img[-p:, :p].reshape(-1, 3), img[-p:, -p:].reshape(-1, 3)])
    backdrop = np.median(corners, axis=0)

    distance = np.linalg.norm(img.astype(np.int16) - backdrop, axis=2)
    return clean_mask(((distance > tolerance) * 255).astype(np.uint8))


def canny(gray: np.ndarray, sigma: float = 0.33) -> np.ndarray:
    """Canny with thresholds derived from the image, not hardcoded."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median = float(np.median(blurred))
    lo = int(max(0, (1.0 - sigma) * median))
    hi = int(min(255, (1.0 + sigma) * median))
    return cv2.Canny(blurred, lo, max(hi, lo + 1), L2gradient=True)


def sobel(gray: np.ndarray, threshold: float = 0.18) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    mag /= (mag.max() or 1.0)
    return ((mag > threshold) * 255).astype(np.uint8)


def extract(path: str | Path, mask_path: str | Path | None = None,
            width: int = 900, method: str = "canny",
            from_backdrop: bool = False) -> Extracted:
    """Reduce an image to (mask, edge map).

    `mask_path`     an explicit car mask, required for photographs.
    `from_backdrop` derive the mask from a flat backdrop, for renders.
    """
    gray = load_gray(path, width)

    if from_backdrop:
        mask = mask_from_backdrop(path, width)
    elif mask_path is not None:
        m = load_gray(mask_path, width)
        mask = clean_mask(((m > 127) * 255).astype(np.uint8))
    else:
        mask = np.full_like(gray, 255)

    edge = canny(gray) if method == "canny" else sobel(gray)
    # only edges on the car count; the rest is scenery
    inner = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    edge = cv2.bitwise_and(edge, inner)
    # the silhouette itself is the single most informative edge
    edge = cv2.bitwise_or(edge, outline_of(mask))
    return Extracted(mask=mask, edge=edge, gray=gray, source=str(path))


def outline_of(mask: np.ndarray) -> np.ndarray:
    eroded = cv2.erode(mask, np.ones((3, 3), np.uint8))
    return cv2.subtract(mask, eroded)
