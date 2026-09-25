"""Clip Natural Earth land to the ADIZ window and simplify.

The artifact sandbox will not let the page fetch raster tiles, so the map has
to carry its own coastline. Natural Earth 1:10m, clipped to the view box and
Douglas-Peucker simplified, costs ~100 KB and never needs the network.
"""
import json, math

BOX = (116.8, 20.4, 124.6, 29.6)          # a little wider than the ADIZ bbox
TOL = 0.0016                               # ≈ 170 m — invisible past z9

def clip(poly, box):
    """Sutherland–Hodgman against a rectangle (a convex window)."""
    w, s, e, n = box
    edges = [(lambda p: p[0] >= w, lambda a, b: ix(a, b, 0, w)),
             (lambda p: p[0] <= e, lambda a, b: ix(a, b, 0, e)),
             (lambda p: p[1] >= s, lambda a, b: ix(a, b, 1, s)),
             (lambda p: p[1] <= n, lambda a, b: ix(a, b, 1, n))]
    out = poly
    for inside, cut in edges:
        if not out:
            return []
        cur, out = out, []
        for i in range(len(cur)):
            a, b = cur[i - 1], cur[i]
            ina, inb = inside(a), inside(b)
            if inb:
                if not ina:
                    out.append(cut(a, b))
                out.append(b)
            elif ina:
                out.append(cut(a, b))
    return out

def ix(a, b, axis, v):
    """Where segment a→b crosses the line (axis == v)."""
    o = 1 - axis
    if b[axis] == a[axis]:
        return [v, a[o]] if axis == 0 else [a[o], v]
    t = (v - a[axis]) / (b[axis] - a[axis])
    q = a[o] + (b[o] - a[o]) * t
    return [v, q] if axis == 0 else [q, v]

def simplify(pts, tol):
    """Douglas–Peucker, iterative."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]; bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        den = math.hypot(dx, dy)
        far, fd = -1, tol
        for k in range(i + 1, j):
            px, py = pts[k]
            d = (abs(dx * (ay - py) - (ax - px) * dy) / den) if den else math.hypot(px - ax, py - ay)
            if d > fd:
                far, fd = k, d
        if far > 0:
            keep[far] = True
            stack += [(i, far), (far, j)]
    return [p for p, k in zip(pts, keep) if k]

def area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i - 1]; x2, y2 = ring[i]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2

rings, src = [], 0
for path in ('ne_10m_land.geojson', 'ne_10m_minor_islands.geojson'):
    for feat in json.load(open(path))['features']:
        g = feat['geometry']
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        for poly in polys:
            for ring in poly:                     # outer ring and any holes
                src += 1
                xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
                if max(xs) < BOX[0] or min(xs) > BOX[2] or max(ys) < BOX[1] or min(ys) > BOX[3]:
                    continue
                c = clip([[p[0], p[1]] for p in ring], BOX)
                if len(c) < 4:
                    continue
                c = simplify(c, TOL)
                if len(c) < 4 or area(c) < 3e-5:   # ~0.3 km² — drop specks
                    continue
                rings.append([[round(x, 4), round(y, 4)] for x, y in c])

rings.sort(key=area, reverse=True)
out = json.dumps(rings, separators=(',', ':'))
open('land_tw.json', 'w').write(out)
print('source rings %d → kept %d · points %d · %.1f KB'
      % (src, len(rings), sum(len(r) for r in rings), len(out) / 1024))
print('largest three areas (deg²):', [round(area(r), 3) for r in rings[:3]])
