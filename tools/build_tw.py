# -*- coding: utf-8 -*-
"""Build the Taiwan ADIZ navigation dataset used by the tracker.

Sources (all fetched from the Taiwan CAA eAIP, https://ais.caa.gov.tw/eaip/):
  ENR 5.2  Taiwan ADIZ lateral limits
  ENR 2.1  Taipei FIR lateral limits
  ENR 4.4  significant points (coordinates) and the routes each point serves
  ENR 4.1  en-route radio navigation aids
  AD 2.2   aerodrome reference points
Route ORDER is not published by the AIP; it is reconstructed as the shortest
open path through each route's published points (see notes in the output).
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = json.load(open(os.path.join(HERE, 'navdata_raw.json'), encoding='utf-8'))
OUT = os.path.join(HERE, '..', 'data')          # this app's data folder
os.makedirs(OUT, exist_ok=True)


def dms(tok):
    """'210000N 1173000E' -> [lon, lat]"""
    lat_s, lon_s = tok.split()
    lat = int(lat_s[0:2]) + int(lat_s[2:4]) / 60 + int(lat_s[4:6]) / 3600
    lon = int(lon_s[0:3]) + int(lon_s[3:5]) / 60 + int(lon_s[5:7]) / 3600
    if lat_s[-1] == 'S':
        lat = -lat
    if lon_s[-1] == 'W':
        lon = -lon
    return [round(lon, 6), round(lat, 6)]


def ring(raw):
    pts = [dms(t) for t in raw]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


zones = []
for key, kind in (('adiz', 'ADIZ'), ('fir', 'FIR')):
    z = RAW[key]
    zones.append({'type': 'Feature',
                  'geometry': {'type': 'Polygon', 'coordinates': [ring(z['raw'])]},
                  'properties': {'id': z['id'], 'kind': kind,
                                 'name_zh': z['name_zh'], 'name_en': z['name_en'],
                                 'source': z['source']}})

WPT = {}
for w in RAW['waypoints']:
    name, lat, lon, typ = w[0], w[1], w[2], w[3]
    WPT[name] = {'name': name, 'lat': lat, 'lon': lon, 'type': typ,
                 'facility': w[4] if len(w) > 4 else None}

# every published aerodrome and navaid must sit inside the ADIZ box or be
# flagged, so nothing silently lands off the map
adiz_ring = zones[0]['geometry']['coordinates'][0]
lons = [p[0] for p in adiz_ring]; lats = [p[1] for p in adiz_ring]
BOX = (min(lons), min(lats), max(lons), max(lats))


def in_box(lon, lat):
    return BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]


def nm(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a['lat'], a['lon'], b['lat'], b['lon']))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(h))


def order_path(names):
    """The AIP lists which points a route serves but not their order.  Take the
    two furthest-apart points as the ends and greedily walk from one to the
    other; report the detour ratio so a suspicious route can be spotted."""
    pts = [WPT[n] for n in names]
    if len(pts) <= 2:
        return names, 1.0
    far, best = None, -1
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = nm(pts[i], pts[j])
            if d > best:
                best, far = d, (i, j)
    start, end = far
    remaining = [k for k in range(len(pts)) if k != start]
    path, cur = [start], start
    while remaining:
        if len(remaining) == 1:
            nxt = remaining[0]
        else:
            cand = [k for k in remaining if k != end] or remaining
            nxt = min(cand, key=lambda k: nm(pts[cur], pts[k]))
        path.append(nxt); remaining.remove(nxt); cur = nxt
    total = sum(nm(pts[path[i]], pts[path[i + 1]]) for i in range(len(path) - 1))
    chord = nm(pts[path[0]], pts[path[-1]])
    return [names[i] for i in path], (total / chord if chord else 1.0)


routes = []
for desig, names in RAW['routes']:
    ordered, ratio = order_path(names)
    routes.append({'designator': desig, 'points': ordered,
                   'path': [[WPT[n]['lon'], WPT[n]['lat']] for n in ordered],
                   'detour_ratio': round(ratio, 3),
                   'order_confidence': 'high' if ratio < 1.15 else 'check'})

aero = []
for a in RAW['aerodromes']:
    icao, iata, zh, en, lat, lon, elev, prov = a
    aero.append({'icao': icao, 'iata': iata, 'name_zh': zh, 'name_en': en,
                 'lat': lat, 'lon': lon, 'elev_ft': elev,
                 'provenance': prov, 'in_adiz': in_box(lon, lat)})

# AIP Taiwan ENR 2.1 publishes each ATS unit's full frequency set, not a
# frequency per sector, so for the Taipei FIR the app can name the controlling
# unit and list its frequencies but cannot say which one applies where.
UNITS = [
    {'id': 'RCAA-ACC', 'name_zh': '臺北區域管制中心', 'name_en': 'Taipei ACC',
     'callsign': 'TAIPEI CONTROL', 'scope': 'fir',
     'freqs': ['122.65', '123.0', '123.6', '125.5', '125.8', '126.5', '126.7',
               '126.9', '127.9', '128.7', '129.1', '130.3', '130.6'],
     'emergency': '121.5', 'hours': 'H24',
     'source': 'AIP Taiwan ENR 2.1'},
    {'id': 'RCAA-APP-TPE', 'name_zh': '臺北進場管制', 'name_en': 'Taipei Approach',
     'callsign': 'TAIPEI APPROACH', 'scope': 'tma',
     'freqs': ['119.5', '119.6', '119.7', '123.5', '124.2', '125.1', '125.6',
               '128.5', '129.6', '130.1', '135.8'],
     'emergency': '121.5', 'hours': 'H24', 'tma': '臺北終端管制區 Taipei TMA',
     'source': 'AIP Taiwan ENR 2.1'},
    {'id': 'RCAA-APP-KHH', 'name_zh': '高雄進場管制', 'name_en': 'Kaohsiung Approach',
     'callsign': 'KAOHSIUNG APPROACH', 'scope': 'tma',
     'freqs': ['119.5', '120.4', '120.6', '120.7', '121.1', '124.7', '125.7',
               '128.1', '129.9', '135.8'],
     'emergency': '121.5', 'hours': 'H24', 'tma': '高雄終端管制區 Kaohsiung TMA',
     'source': 'AIP Taiwan ENR 2.1'},
]

data = {
    'units': UNITS,
    'zones': {'type': 'FeatureCollection', 'features': zones},
    'waypoints': list(WPT.values()),
    'routes': routes,
    'aerodromes': aero,
    'land': json.load(open(os.path.join(HERE, 'land_tw.json'))),
    'bbox': [round(v, 4) for v in BOX],
    'sources': {
        'adiz': RAW['adiz']['source'], 'fir': RAW['fir']['source'],
        'points': 'AIP Taiwan ENR 4.4 (significant points) & ENR 4.1 (navaids)',
        'aerodromes': 'AIP Taiwan AD 2.2 ARP (prov=aip); other fields marked prov=ref',
        'land': 'Natural Earth 1:10m land & minor islands, clipped to the view box and simplified to ~170 m (public domain)',
        'route_order': 'AIP Taiwan publishes route membership (ENR 4.4) but not the '
                       'order of points; order reconstructed as the shortest open path.',
        'not_included': 'M503 / N884 / A470 are mainland routes west of the median line, '
                        'not published in Taiwan’s AIP; omitted rather than guessed.',
    },
}
json.dump(data, open(os.path.join(OUT, 'taiwan_navdata.json'), 'w'),
          ensure_ascii=False, separators=(',', ':'))

print('ADIZ bbox lon %.2f..%.2f  lat %.2f..%.2f' % (BOX[0], BOX[2], BOX[1], BOX[3]))
print('waypoints %d  routes %d  aerodromes %d (%d inside ADIZ)'
      % (len(WPT), len(routes), len(aero), sum(1 for a in aero if a['in_adiz'])))
low = [(r['designator'], r['detour_ratio']) for r in routes if r['order_confidence'] != 'high']
print('routes whose reconstructed order needs a look:', low or 'none')
print('outside ADIZ box:', [a['icao'] for a in aero if not a['in_adiz']] or 'none')
print('file KB', os.path.getsize(os.path.join(OUT, 'taiwan_navdata.json')) // 1024)
