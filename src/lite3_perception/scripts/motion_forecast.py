# SPDX-License-Identifier: BSD-3-Clause
"""Small observed XY clusters, constant-velocity forecast; no Gazebo truth input.

This is a short-term conservative occupancy estimate, not object recognition.
Only compact, consistently observed moving clusters are forecast. The real
obstacle and clearing clouds remain unchanged.
"""
from collections import deque

import numpy as np


class MotionForecast:
    def __init__(self, horizon=2.5, padding=.10):
        self.horizon = horizon
        self.padding = padding
        self.tracks = []
        self.last_time = None
        self.moving = []

    @staticmethod
    def clusters(points):
        if not len(points):
            return []
        cells = np.unique(np.floor(points[:, :2] / .08).astype(int), axis=0)
        remaining = {tuple(p) for p in cells}
        result = []
        while remaining:
            stack = [remaining.pop()]
            component = []
            while stack:
                p = stack.pop()
                component.append(p)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        q = (p[0]+dx, p[1]+dy)
                        if q in remaining:
                            remaining.remove(q)
                            stack.append(q)
            xy = np.asarray(component) * .08
            lo, hi = xy.min(axis=0), xy.max(axis=0)+.08
            extent = hi-lo
            # Walls, isolated returns and large joined structures aren't tracks.
            if len(xy) >= 4 and .24 <= max(extent) <= 1.6 and min(extent) >= .16:
                result.append((lo, hi))
        return result

    def update(self, points, stamp):
        if self.last_time is not None and not 0 < stamp-self.last_time <= .5:
            self.tracks = []
        self.last_time = stamp
        detections = self.clusters(points)
        centers = [(lo+hi)/2 for lo, hi in detections]
        candidates = []
        for i, track in enumerate(self.tracks):
            for j, center in enumerate(centers):
                distance = np.linalg.norm(center-track['history'][-1][1])
                if distance < .35:
                    candidates.append((distance, i, j))
        matched, used = {}, set()
        for _, i, j in sorted(candidates):
            if i not in matched and j not in used:
                matched[i] = j
                used.add(j)
        tracks = []
        for i, j in matched.items():
            track = self.tracks[i]
            track['history'].append((stamp, centers[j]))
            track['shapes'].append(detections[j])
            track['bounds'] = detections[j]
            tracks.append(track)
        for j in range(len(detections)):
            if j not in used:
                tracks.append({'history': deque([(stamp, centers[j])], maxlen=9),
                               'shapes': deque([detections[j]], maxlen=9),
                               'bounds': detections[j]})
        self.tracks = tracks
        self.moving = []
        forecast = []
        for track in tracks:
            history = track['history']
            if len(history) < 6 or stamp-history[0][0] < .5:
                continue
            times = np.array([s[0]-stamp for s in history])
            xy = np.array([s[1] for s in history])
            design = np.column_stack([times, np.ones(len(times))])
            model = np.linalg.lstsq(design, xy, rcond=None)[0]
            velocity = model[0]
            residual = np.sqrt(np.mean((design @ model-xy)**2))
            speed = np.linalg.norm(velocity)
            if not .08 <= speed <= .8 or residual > .035:
                continue
            # A static object's visible part can grow/shrink as the robot moves.
            # Require both opposite observed bounds to translate consistently;
            # centroid drift caused by changing occlusion isn't enough.
            bounds = np.array(track['shapes'])
            edges = np.linalg.lstsq(design, bounds.reshape(len(times), 4), rcond=None)[0][0].reshape(2, 2)
            if np.linalg.norm(edges[0]-edges[1]) > .10:
                continue
            extents = bounds[:, 1]-bounds[:, 0]
            if np.max(np.ptp(extents, axis=0)) > .081:
                continue
            lo, hi = track['bounds']
            self.moving.append({'center': ((lo+hi)/2).tolist(),
                                'velocity': velocity.tolist(), 'residual': float(residual)})
            for dt in np.arange(0, self.horizon+.01, .25):
                a = lo + velocity*dt - self.padding
                b = hi + velocity*dt + self.padding
                x, y = np.meshgrid(np.arange(a[0], b[0]+.025, .05),
                                   np.arange(a[1], b[1]+.025, .05))
                forecast.append(np.column_stack([x.ravel(), y.ravel(), np.full(x.size, .3)]))
        return np.vstack(forecast).astype(np.float32) if forecast else np.empty((0, 3), np.float32)
