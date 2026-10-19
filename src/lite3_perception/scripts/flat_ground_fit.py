"""Bounded robust plane fit for the explicitly flat-ground simulation mode.

Classifies a scan; never alters coordinates, TF or measured ray origins.
"""
import numpy as np


def fit_ground_plane(points, origin, ground=.005, tolerance=.012,
                     max_tilt=.035, max_origin_error=.02):
    """Return z=a*x+b*y+c, or None when ground evidence is insufficient.

The plane must span two metres in X/Y, be close to known horizontal ground,
    and explain at least 80 spatially distinct observations. Low objects are
    outliers rather than a reason to raise the configured obstacle height.
    """
    points = np.asarray(points, dtype=float)
    origin = np.asarray(origin, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 80:
        return None
    distance = np.linalg.norm(points[:, :2]-origin[:2], axis=1)
    mask = np.isfinite(points).all(axis=1) & (distance >= .4) & (distance <= 8.)
    mask &= np.abs(points[:, 2]-ground) <= .18
    p = points[mask]
    if len(p) < 80:
        return None
    # One lowest return per 12cm XY cell prevents dense near returns dominating.
    cell = np.floor(p[:, :2]/.12).astype(np.int64)
    order = np.lexsort((p[:, 2], cell[:, 1], cell[:, 0]))
    ordered = cell[order]
    keep = np.r_[True, np.any(ordered[1:] != ordered[:-1], axis=1)]
    p = p[order[keep]]
    if len(p) > 1800:
        p = p[np.linspace(0, len(p)-1, 1800).astype(int)]
    if len(p) < 80:
        return None
    xy1 = np.column_stack([p[:, :2], np.ones(len(p))])
    rng = np.random.default_rng(712)
    best = None
    best_count = 0
    for _ in range(48):
        ids = rng.choice(len(p), 3, replace=False)
        try:
            plane = np.linalg.solve(xy1[ids], p[ids, 2])
        except np.linalg.LinAlgError:
            continue
        if np.linalg.norm(plane[:2]) > max_tilt:
            continue
        if abs(np.dot(np.r_[origin[:2], 1.], plane)-ground) > max_origin_error:
            continue
        residual = np.abs(xy1 @ plane-p[:, 2])
        inliers = residual < tolerance
        count = int(inliers.sum())
        if count > best_count:
            best, best_count = inliers, count
    if best is None or best_count < max(80, int(.35*len(p))):
        return None
    for _ in range(3):
        plane = np.linalg.lstsq(xy1[best], p[best, 2], rcond=None)[0]
        best = np.abs(xy1 @ plane-p[:, 2]) < tolerance
        if best.sum() < 80:
            return None
    support = p[best]
    if np.ptp(support[:, 0]) < 2. or np.ptp(support[:, 1]) < 2.:
        return None
    if np.linalg.norm(plane[:2]) > max_tilt or abs(
            np.dot(np.r_[origin[:2], 1.], plane)-ground) > max_origin_error:
        return None
    return plane


def height_above_plane(points, plane, ground=.005):
    """Height in the existing absolute-height convention; XY remains untouched."""
    return points[:, 2]-(points[:, 0]*plane[0]+points[:, 1]*plane[1]+plane[2])+ground
