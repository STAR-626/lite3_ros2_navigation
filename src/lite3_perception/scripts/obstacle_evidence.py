"""Reject isolated returns and require a second scan before obstacle marking.

Measured clearing rays are deliberately not modified or filtered here.
"""
from itertools import product
import numpy as np


class ObstacleEvidence:
    def __init__(self, cell_size=.08, min_support=3, max_gap=.3):
        self.cell_size=cell_size;self.min_support=min_support;self.max_gap=max_gap
        self.previous=set();self.stamp=None

    def filter(self, points, stamp):
        points=np.asarray(points)
        mask=np.zeros(len(points),dtype=bool)
        if self.stamp is None or stamp<=self.stamp or stamp-self.stamp>self.max_gap:
            self.previous=set()
        if not len(points):
            self.previous=set();self.stamp=stamp;return mask
        cells=np.floor(points/self.cell_size).astype(np.int64)
        unique,inverse,counts=np.unique(cells,axis=0,return_inverse=True,return_counts=True)
        table={tuple(cell):int(count)for cell,count in zip(unique,counts)}
        offsets=list(product([-1,0,1],repeat=3))
        good=np.array([sum(table.get((int(c[0])+dx,int(c[1])+dy,int(c[2])+dz),0)
                           for dx,dy,dz in offsets)>=self.min_support for c in unique])
        supported=good[inverse]
        xy=np.floor(points[:,:2]/self.cell_size).astype(np.int64)
        for idx in np.flatnonzero(supported):
            x,y=xy[idx]
            mask[idx]=any((int(x)+dx,int(y)+dy)in self.previous
                          for dx,dy in product([-1,0,1],repeat=2))
        self.previous={tuple(cell)for cell in xy[supported]};self.stamp=stamp
        return mask
