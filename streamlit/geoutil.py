# -*- coding: utf-8 -*-
"""Pure-stdlib geometry helpers — no numpy/shapely needed, so the app installs
cleanly on Streamlit Community Cloud."""
from __future__ import annotations
import math

FT_PER_M = 1.0 / 0.3048


# --------------------------------------------------------------------------- #
#  point in polygon
# --------------------------------------------------------------------------- #
def point_in_ring(lon: float, lat: float, ring) -> bool:
    """Ray-casting test.  `ring` is a closed list of [lon, lat]."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def in_bbox(lon, lat, bb) -> bool:
    return bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]


# --------------------------------------------------------------------------- #
#  great circle
# --------------------------------------------------------------------------- #
R_EARTH_NM = 3440.065


def gc_point(lat1, lon1, lat2, lon2, f):
    """Fraction `f` (0..1) along the great circle from 1 to 2."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(
        math.sin((p2 - p1) / 2) ** 2 +
        math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    if d == 0:
        return lat1, lon1
    a = math.sin((1 - f) * d) / math.sin(d)
    b = math.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return (math.degrees(math.atan2(z, math.sqrt(x * x + y * y))),
            math.degrees(math.atan2(y, x)))


def gc_distance_nm(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_NM * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# --------------------------------------------------------------------------- #
#  3D prism geometry for deck.gl
# --------------------------------------------------------------------------- #
def prism_geometry(ring, lower_m, upper_m, vscale):
    """Return (top_ring3d, bottom_ring3d, struts) in deck.gl [lon, lat, z] form.

    deck.gl tessellates polygons in the XY plane, so a truly vertical wall
    polygon would collapse to zero area.  We therefore draw the airspace block
    as two translucent horizontal caps plus a 3-D wireframe (top ring, bottom
    ring, and one vertical strut per vertex), which renders correctly on every
    deck.gl version and stays fast on phones.
    """
    zt = (upper_m or 0) * vscale
    zb = (lower_m or 0) * vscale
    top = [[p[0], p[1], zt] for p in ring]
    bot = [[p[0], p[1], zb] for p in ring]
    struts = [[[p[0], p[1], zb], [p[0], p[1], zt]] for p in ring[:-1]]
    return top, bot, struts


# --------------------------------------------------------------------------- #
#  formatting
# --------------------------------------------------------------------------- #
def m_to_ft(m):
    return None if m is None else int(round(m * FT_PER_M))


def fmt_level(m, lang='bi'):
    """'7 800 m / FL256' style label."""
    if m is None:
        return '—'
    ft = m_to_ft(m)
    if m == 0:
        return {'cn': '地面 GND', 'en': 'GND', 'bi': '地面 GND'}[lang]
    fl = int(round(ft / 100.0))
    return '%s m / %s ft (FL%03d)' % (f'{m:,}'.replace(',', ' '), f'{ft:,}', fl)


def fmt_dms(lon, lat):
    def one(v, is_lat):
        h = ('N' if v >= 0 else 'S') if is_lat else ('E' if v >= 0 else 'W')
        v = abs(v)
        d = int(v); m = int((v - d) * 60); s = (v - d - m / 60) * 3600
        w = 2 if is_lat else 3
        return '%s%0*d°%02d\'%04.1f"' % (h, w, d, m, s)
    return one(lat, True) + ' ' + one(lon, False)


def fmt_limit(m, ref=None, lang='bi'):
    """Format a published vertical limit, keeping its pressure reference.
    QNE = standard-pressure level (what ADS-B reports); QNH = altitude on the
    local altimeter setting, used below the transition altitude."""
    if m is None:
        return '\u2014'
    if m == 0 or ref == 'GND':
        return '\u5730\u9762 GND'
    if ref == 'QNH':          # an altimeter-setting altitude is not a flight level
        return 'QNH %s m / %s ft' % (f'{m:,}'.replace(',', ' '), f'{m_to_ft(m):,}')
    return fmt_level(m, lang)
