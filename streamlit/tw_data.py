# -*- coding: utf-8 -*-
"""臺灣防空識別區資料層 — Taiwan ADIZ data layer.

Loads the dataset built by `tools/build_tw.py` (AIP Taiwan: ADIZ, Taipei FIR,
significant points, navaids, routes, aerodromes, plus a clipped Natural Earth
coastline) and the ATC sectors west of the Strait parsed from AIP CHINA, and
answers the one question the map exists to answer: which unit, and on what
frequency, is working an aircraft at this position and altitude.
"""
from __future__ import annotations
import json
import os

from geoutil import point_in_ring, in_bbox

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')        # one dataset, both front ends


def load():
    """Returns (nav, sectors).  Cheap enough to memoise in the caller."""
    with open(os.path.join(DATA, 'taiwan_navdata.json'), encoding='utf-8') as fh:
        nav = json.load(fh)
    with open(os.path.join(DATA, 'sectors_tw.json'), encoding='utf-8') as fh:
        sectors = json.load(fh)
    return nav, sectors


def zone_ring(nav, kind):
    for f in nav['zones']['features']:
        if f['properties']['kind'] == kind:
            return f['geometry']['coordinates'][0]
    return []


# --------------------------------------------------------------------------- #
#  controlling unit
# --------------------------------------------------------------------------- #
def _vertical_has(s, alt_m):
    """AIP semantics: a published ceiling is included, an `(exclusive)` bound is
    not.  An aircraft with no usable altitude matches nothing."""
    if alt_m is None or s['upper_m'] is None:
        return False
    lo = s['lower_m'] or 0
    hi = s['upper_m']
    above = alt_m > lo if s['lower_exclusive'] else alt_m >= lo
    below = alt_m < hi if s['upper_exclusive'] else alt_m <= hi
    return above and below


def controlling_unit(nav, sectors, lon, lat, alt_m):
    """The unit working this position/level.

    Sectorised frequencies exist only west of the Strait — AIP CHINA publishes
    them per sector, AIP Taiwan publishes only each unit's full frequency list.
    So inside the Taipei FIR the answer is the unit and its published set.
    Approach/terminal wins over area control, and a smaller volume wins over a
    larger one, which is how the AIP's "Exclude ..." notes actually behave.
    """
    fir = zone_ring(nav, 'FIR')
    in_fir = point_in_ring(lon, lat, fir)

    hits = [s for s in sectors
            if in_bbox(lon, lat, s['bbox']) and point_in_ring(lon, lat, s['ring'])]
    ok = sorted((s for s in hits if _vertical_has(s, alt_m)),
                key=lambda s: ((0 if s['kind'] == 'APP' else 1) * 1e9) + s['area_km2'])
    if ok:
        s = ok[0]
        return {'kind': 'sector', 'sector': s,
                'unit': '%s / %s' % (s['acc_cn'], s['acc_en']),
                'callsign': s['callsign_en'], 'freq': s['freq_mhz'],
                'sec': s['freq_sec_mhz'], 'detail': s['id'], 'in_fir': in_fir}
    if in_fir:
        u = next((x for x in nav['units'] if x['scope'] == 'fir'), None)
        if u:
            return {'kind': 'fir', 'unit': '%s / %s' % (u['name_zh'], u['name_en']),
                    'callsign': u['callsign'], 'freqs': u['freqs'],
                    'emergency': u['emergency'], 'in_fir': True}
    return {'kind': 'none', 'in_fir': in_fir}


def freq_text(u):
    """One line for a table cell."""
    if u['kind'] == 'sector':
        return '%s MHz' % (u['freq'] or '—')
    if u['kind'] == 'fir':
        return '%s（%d 個公布頻率）' % (u['freqs'][0], len(u['freqs']))
    return '—'


def in_adiz(nav, lon, lat):
    return point_in_ring(lon, lat, zone_ring(nav, 'ADIZ'))


def airport_of(nav, code):
    if not code:
        return None
    return next((a for a in nav['aerodromes']
                 if a['icao'] == code or a['iata'] == code), None)
