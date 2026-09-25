# -*- coding: utf-8 -*-
"""deck.gl layer payloads for the Taiwan ADIZ traffic map.

Every layer here is a plain list of dicts; pydeck only needs the field names.
Each row that should answer a hover carries a `tip` string, so one tooltip
template serves the whole map.
"""
from __future__ import annotations

from assets import PLANE_PNG, PLANE_SIZE
from geoutil import fmt_level, fmt_limit

# Dark theme first — the light values are the same hues lifted off the page.
THEME = {
    'dark': {
        'land': [20, 30, 41], 'coast': [66, 89, 109],
        'awy': [51, 80, 106], 'wpt': [62, 86, 107], 'apt': [205, 216, 226],
        'adiz': [224, 90, 78], 'fir': [79, 158, 224],
        'ac': [245, 180, 0], 'ac_sel': [255, 255, 255], 'ac_gnd': [107, 125, 142],
        'ink': [232, 238, 244], 'ground': [7, 11, 16],
    },
    'light': {
        'land': [221, 228, 235], 'coast': [157, 176, 192],
        'awy': [147, 168, 189], 'wpt': [164, 181, 196], 'apt': [44, 57, 68],
        'adiz': [201, 55, 44], 'fir': [42, 120, 214],
        'ac': [201, 133, 0], 'ac_sel': [13, 20, 27], 'ac_gnd': [132, 150, 166],
        'ink': [13, 20, 27], 'ground': [238, 241, 244],
    },
}

ICON = {'url': PLANE_PNG, 'width': PLANE_SIZE, 'height': PLANE_SIZE,
        'anchorX': PLANE_SIZE // 2, 'anchorY': PLANE_SIZE // 2, 'mask': True}


def _ring_rows(nav, kind, colour, name):
    ring = None
    for f in nav['zones']['features']:
        if f['properties']['kind'] == kind:
            ring = f['geometry']['coordinates'][0]
            props = f['properties']
            break
    if ring is None:
        return []
    tip = ('<div style="font:13px/1.5 system-ui"><b>%s</b><br>%s<br>'
           '<span style="opacity:.65">%s</span></div>'
           % (props['name_zh'], props['name_en'], props['source']))
    return [{'polygon': ring, 'colour': colour, 'name': name, 'tip': tip}]


def land(nav, T):
    """The coastline carried inside the app — no tiles, no network."""
    return [{'polygon': r} for r in nav.get('land', [])], T['land'], T['coast']


def zones(nav, T, show_adiz=True, show_fir=True):
    rows = []
    if show_adiz:
        rows += _ring_rows(nav, 'ADIZ', T['adiz'], 'ADIZ')
    if show_fir:
        rows += _ring_rows(nav, 'FIR', T['fir'], 'FIR')
    return rows


def sectors(sects, T, alt_m=None):
    """2-D footprints of the AIP CHINA sectors that reach into the zone.

    With a level given, only the sectors that contain that level are drawn —
    airspace is stacked, and a flat plan of every layer at once is unreadable.
    """
    rows = []
    for s in sects:
        if alt_m is not None:
            lo, hi = s['lower_m'] or 0, s['upper_m']
            if hi is None:
                continue
            above = alt_m > lo if s['lower_exclusive'] else alt_m >= lo
            below = alt_m < hi if s['upper_exclusive'] else alt_m <= hi
            if not (above and below):
                continue
        kind = '進場／終端 APP' if s['kind'] == 'APP' else '區域 ACC'
        sec = ('　備用 <b>%s</b>' % s['freq_sec_mhz']) if s['freq_sec_mhz'] else ''
        rows.append({
            'polygon': s['ring'], 'colour': s['colour'], 'id': s['id'],
            'tip': ('<div style="font:13px/1.5 system-ui"><b>%s</b>　'
                    '<span style="opacity:.65">%s</span><br>%s / %s<br>'
                    '垂直 %s → %s<br>主頻 <b>%s MHz</b>%s</div>')
                   % (s['id'], kind, s['acc_cn'], s['acc_en'],
                      fmt_limit(s['upper_m'], s.get('upper_ref')),
                      fmt_limit(s['lower_m'], s.get('lower_ref')),
                      s['freq_mhz'] or '—', sec),
        })
    return rows


def airways(nav):
    rows, labels = [], []
    for r in nav['routes']:
        conf = ('<div style="color:#f5b400">點序信心較低，AIP 未公布順序</div>'
                if r.get('order_confidence') != 'high' else '')
        tip = ('<div style="font:13px/1.5 system-ui"><b>%s</b><br>%s<br>'
               '<span style="opacity:.65">%d 個航路點 · AIP Taiwan ENR 4.4</span>%s</div>'
               % (r['designator'], ' → '.join(r['points']), len(r['points']), conf))
        rows.append({'path': r['path'], 'designator': r['designator'], 'tip': tip})
        mid = r['path'][len(r['path']) // 2]
        labels.append({'position': mid, 'text': r['designator']})
    return rows, labels


def waypoints(nav):
    rows = []
    for w in nav['waypoints']:
        kind = w['type'].upper()
        fac = ('　%s' % w['facility']) if w.get('facility') else ''
        rows.append({'position': [w['lon'], w['lat']], 'name': w['name'],
                     'tip': '<div style="font:13px/1.5 system-ui"><b>%s</b><br>%s%s</div>'
                            % (w['name'], kind, fac)})
    return rows


def aerodromes(nav):
    rows = []
    for a in nav['aerodromes']:
        elev = ('　標高 %d ft' % a['elev_ft']) if a.get('elev_ft') is not None else ''
        src = 'AIP Taiwan AD 2.2' if a['provenance'] == 'aip' else '參考值 reference'
        rows.append({'position': [a['lon'], a['lat']], 'icao': a['icao'],
                     'tip': ('<div style="font:13px/1.5 system-ui"><b>%s / %s</b><br>%s<br>%s'
                             '<br><span style="opacity:.65">%s</span></div>')
                            % (a['icao'], a['iata'] or '—', a['name_zh'],
                               a['name_en'] + elev, src)})
    return rows


def aircraft(flights, T, selected=None, freq_of=None):
    """One row per aircraft, coloured by state and carrying its own tooltip."""
    rows = []
    for f in flights:
        sel = selected is not None and f['hex'] == selected
        on_ground = (f.get('alt_m') or 0) <= 0 and not f.get('demo')
        colour = T['ac_sel'] if sel else (T['ac_gnd'] if on_ground else T['ac'])
        freq = freq_of(f) if freq_of else ''
        route = ''
        if f.get('dep') or f.get('arr'):
            route = '%s → %s<br>' % (f.get('dep') or '—', f.get('arr') or '—')
        rows.append({
            'position': [f['lon'], f['lat']],
            'angle': -(f.get('track') or 0),
            'size': 30 if sel else 22,
            'colour': list(colour),
            'icon': ICON,
            'callsign': f['callsign'],
            'hex': f['hex'],
            'tip': ('<div style="font:13px/1.5 system-ui"><b>%s</b>　'
                    '<span style="opacity:.65">%s %s</span><br>%s%s　%s kt<br>'
                    '<b>%s</b></div>')
                   % (f['callsign'], f.get('type') or '', f.get('registration') or '',
                      route, fmt_level(f.get('alt_m')), f.get('gs_kt') or '—', freq),
        })
    return rows


def labels(rows, key='callsign'):
    return [{'position': r['position'], 'text': r[key]} for r in rows]
