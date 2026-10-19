# Copyright 2026 STAR-626
# SPDX-License-Identifier: BSD-3-Clause
"""Decode only verified Gazebo organized GPU-lidar +infinity-range samples.

A no-return ray is free evidence up to the configured maximum range, not an
obstacle hit. Arbitrary NaNs, negative ranges and mismatched geometry are not
converted. This helper is deliberately specific to the configured simulator.
"""
import math
import numpy as np


def clearing_no_returns(points, width, height, horizontal_samples, vertical_samples,
                        horizontal_min, horizontal_max, vertical_min, vertical_max,
                        range_max):
    """Return max-range endpoints for the matching signed-infinity pattern.

    Preserve original row/column ordering before finite-point filtering. Both
    original frame and stamp are retained by the caller. No interpolation across
    missing scan bins or real hit endpoints is performed.
    """
    empty = np.empty((0, 3), dtype=np.float32)
    if (width != horizontal_samples or height != vertical_samples or
            width < 2 or height < 2 or len(points) != width*height):
        return empty
    if not all(math.isfinite(float(v)) for v in
               (horizontal_min, horizontal_max, vertical_min, vertical_max, range_max)):
        return empty
    if range_max <= 0 or horizontal_max <= horizontal_min or vertical_max <= vertical_min:
        return empty
    p = np.asarray(points).reshape(-1, 3)
    # GPU lidar emits signed infinities (and NaN for zero direction components)
    # for +infinity range. An all-NaN sample is invalid, not a no-return beam.
    candidate = (~np.isfinite(p).any(axis=1)) & (np.isinf(p).sum(axis=1) >= 2)
    indices = np.flatnonzero(candidate)
    if len(indices) == 0:
        return empty
    h = horizontal_min + indices % width * (horizontal_max-horizontal_min)/(width-1)
    v = vertical_min + indices // width * (vertical_max-vertical_min)/(height-1)
    directions = np.column_stack((np.cos(v)*np.cos(h), np.cos(v)*np.sin(h), np.sin(v)))
    # Validate axes far from zero. Near-zero axes can be NaN or signed infinity
    # because Gazebo uses float trigonometry. Reject sign-inverted invalid data.
    constrained = np.abs(directions) > 1e-5
    axes_ok = ~constrained | (np.isinf(p[indices]) &
                              (np.signbit(p[indices]) == np.signbit(directions)))
    valid = axes_ok.all(axis=1)
    # A small inward epsilon prevents float32 norm rounding beyond range_max.
    return (directions[valid] * (range_max-1e-4)).astype(np.float32)


def rays_intersect_body(endpoints, origin, self_min, self_max):
    """Reject free rays that intersect the robot's self-filter AABB in TORSO.

    A self-filtered/occluded direction cannot provide free-space evidence.
    Endpoints and origin must already be in TORSO coordinates.
    """
    p = np.asarray(endpoints, dtype=float).reshape(-1, 3)
    origin = np.broadcast_to(np.asarray(origin, dtype=float), p.shape)
    direction = p-origin
    low, high = np.asarray(self_min), np.asarray(self_max)
    t_enter = np.zeros(len(p)); t_exit = np.ones(len(p))
    for axis in range(3):
        parallel = np.abs(direction[:, axis]) < 1e-10
        outside = (origin[:, axis] < low[axis]) | (origin[:, axis] > high[axis])
        t_exit[parallel & outside] = -1.
        denominator = np.where(parallel, 1., direction[:, axis])
        a = (low[axis]-origin[:, axis])/denominator
        b = (high[axis]-origin[:, axis])/denominator
        t_enter = np.maximum(t_enter, np.where(parallel, -np.inf, np.minimum(a,b)))
        t_exit = np.minimum(t_exit, np.where(parallel, np.inf, np.maximum(a,b)))
    return t_enter <= t_exit
