# -*- coding: utf-8 -*-
"""Live traffic + route lookup for the Taiwan ADIZ, with a self-contained demo
generator so the app always has something to draw (offline, rate-limited, or
behind a firewall).

Streamlit fetches server-side, so the CORS wall that forces the standalone HTML
page onto ADS-B Exchange does not apply here: the keyless community feeds work
directly."""
from __future__ import annotations
import json, math, time, urllib.request, urllib.error

from geoutil import gc_point, gc_distance_nm, bearing

UA = 'taiwan-adiz-traffic/1.0 (airspace visualiser)'
TIMEOUT = 12

# --------------------------------------------------------------------------- #
#  Live sources (both are free, keyless, community ADS-B networks)
# --------------------------------------------------------------------------- #
SOURCES = {
    'adsb.lol': {
        'point': 'https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}',
        'routeset': 'https://api.adsb.lol/api/0/routeset',
        'label': 'adsb.lol（免費，無需金鑰）',
    },
    'airplanes.live': {
        'point': 'https://api.airplanes.live/v2/point/{lat}/{lon}/{dist}',
        'routeset': None,
        'label': 'airplanes.live（免費，無需金鑰）',
    },
}
# Two 250 NM discs cover the ADIZ box (117.5-123E, 21-29N) with overlap to
# spare: one over the southern Strait, one over the northern approaches.
QUERY_CENTRES = [(23.0, 120.0, 250), (27.2, 120.3, 250)]


_last_call = [0.0]
MIN_GAP = 1.3          # adsb.lol rate-limits to roughly one request per second


def _throttle():
    wait = MIN_GAP - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _get_json(url, data=None):
    _throttle()
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read().decode('utf-8', 'replace')
    if not body.lstrip().startswith(('{', '[')):
        raise RuntimeError('rate limited or non-JSON response')
    return json.loads(body)


def _alt_m(ac):
    """ADS-B barometric altitude (ft, 1013.2 hPa) -> metres, matching the AIP's
    metric standard-pressure levels.  'ground' becomes 0."""
    v = ac.get('alt_baro')
    if v in (None, 'ground'):
        return 0.0 if v == 'ground' else None
    try:
        return float(v) * 0.3048
    except (TypeError, ValueError):
        return None


def fetch_live(source='adsb.lol', centres=None):
    """Return (flights, errors).  Never raises."""
    cfg = SOURCES[source]
    seen, out, errs = {}, [], []
    for lat, lon, dist in (centres or QUERY_CENTRES):
        js = None
        for attempt in range(2):                      # one retry past a rate limit
            try:
                js = _get_json(cfg['point'].format(lat=lat, lon=lon, dist=dist))
                break
            except Exception as exc:                  # noqa: BLE001
                if attempt:
                    errs.append('%s @%.1f/%.1f: %s' % (source, lat, lon, exc))
                else:
                    time.sleep(MIN_GAP)
        if js is None:
            continue
        for ac in js.get('ac') or js.get('aircraft') or []:
            hexid = (ac.get('hex') or '').strip()
            if not hexid or hexid in seen:
                continue
            if ac.get('lat') is None or ac.get('lon') is None:
                continue
            seen[hexid] = True
            out.append({
                'hex': hexid,
                'callsign': (ac.get('flight') or '').strip() or hexid.upper(),
                'registration': (ac.get('r') or '').strip(),
                'type': (ac.get('t') or '').strip(),
                'lat': float(ac['lat']), 'lon': float(ac['lon']),
                'alt_m': _alt_m(ac),
                'gs_kt': ac.get('gs'), 'track': ac.get('track'),
                'vs_fpm': ac.get('baro_rate') or ac.get('geom_rate'),
                'squawk': ac.get('squawk'),
                'source': source, 'demo': False,
                'dep': None, 'arr': None, 'dep_name': None, 'arr_name': None,
            })
    return out, errs


def fetch_routes(flights, source='adsb.lol'):
    """Fill dep/arr from adsb.lol's route database (callsign -> airport pair)."""
    url = SOURCES['adsb.lol']['routeset']
    todo = [f for f in flights if f['callsign'] and not f['callsign'].startswith('~')]
    errs = []
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        body = {'planes': [{'callsign': f['callsign'], 'lat': f['lat'], 'lng': f['lon']}
                           for f in batch]}
        try:
            res = _get_json(url, body)
        except Exception as exc:                      # noqa: BLE001
            errs.append('routeset: %s' % exc)
            break
        by_cs = {}
        for r in res if isinstance(res, list) else []:
            by_cs[(r.get('callsign') or '').strip()] = r
        for f in batch:
            r = by_cs.get(f['callsign'])
            if not r:
                continue
            aps = r.get('_airports') or []
            if len(aps) >= 2:
                f['dep'] = aps[0].get('icao') or aps[0].get('iata')
                f['arr'] = aps[-1].get('icao') or aps[-1].get('iata')
                f['dep_name'] = aps[0].get('name')
                f['arr_name'] = aps[-1].get('name')
            elif r.get('_airport_codes_iata'):
                parts = r['_airport_codes_iata'].split('-')
                if len(parts) >= 2:
                    f['dep'], f['arr'] = parts[0], parts[-1]
    return errs


# --------------------------------------------------------------------------- #
#  Demo traffic — deterministic from the clock, so it animates between reruns
# --------------------------------------------------------------------------- #
_AP = {
    # Taiwan (AIP Taiwan AD 2.2 ARPs)
    'RCTP': (25.08028, 121.23222), 'RCSS': (25.06972, 121.5525),
    'RCKH': (22.57694, 120.35028), 'RCMQ': (24.265, 120.62083),
    'RCNN': (22.94917, 120.21111), 'RCYU': (24.02333, 121.61),
    'RCFN': (22.75528, 121.10028), 'RCQC': (23.56861, 119.62833),
    'RCBS': (24.42889, 118.36111), 'RCFG': (26.15972, 119.95833),
    'RCGI': (22.67333, 121.46611), 'RCLY': (22.02778, 121.53472),
    'RCKU': (23.45444, 120.40333),
    # mainland coast, for cross-Strait legs
    'ZSAM': (24.544, 118.1277), 'ZSFZ': (25.9351, 119.6633),
    'ZSQZ': (24.7964, 118.5897), 'ZSWZ': (27.9122, 120.8522),
    'ZSPD': (31.1434, 121.8052), 'ZGGG': (23.3924, 113.2988),
    # the traffic that actually crosses the ADIZ
    'RJAA': (35.7647, 140.3864), 'RJBB': (34.4273, 135.2440),
    'RJFF': (33.5859, 130.4510), 'ROAH': (26.1958, 127.6458),
    'RKSI': (37.4691, 126.4505), 'VHHH': (22.3080, 113.9185),
    'RPLL': (14.5086, 121.0198), 'WSSS': (1.3644, 103.9915),
    'VTBS': (13.6900, 100.7501), 'KLAX': (33.9416, -118.4085),
}
_DEMO_ROUTES = [
    ('CAL742', 'B738', 'RCTP', 'RJAA'), ('EVA189', 'B789', 'RCTP', 'VHHH'),
    ('CAL202', 'A333', 'RCTP', 'RJBB'), ('EVA116', 'A321', 'RCTP', 'ROAH'),
    ('CAL504', 'B738', 'RCTP', 'ZSPD'), ('CPA407', 'A359', 'VHHH', 'RCTP'),
    ('ANA852', 'B788', 'RJAA', 'RCTP'), ('KAL691', 'B77W', 'RKSI', 'RCTP'),
    ('SIA877', 'B77W', 'WSSS', 'RCTP'), ('THA632', 'B788', 'VTBS', 'RCTP'),
    ('PAL891', 'A321', 'RPLL', 'RCTP'), ('JAL812', 'B767', 'RJFF', 'RCTP'),
    ('CAL811', 'B744', 'RCTP', 'KLAX'), ('EVA371', 'A333', 'RCTP', 'RCKH'),
    ('UIA231', 'ATR7', 'RCSS', 'RCQC'), ('UIA871', 'ATR7', 'RCKH', 'RCFG'),
    ('MDA307', 'ATR7', 'RCSS', 'RCBS'), ('DAC7511', 'DH8D', 'RCSS', 'RCFN'),
    ('UIA192', 'ATR7', 'RCQC', 'RCSS'), ('MDA632', 'ATR7', 'RCFG', 'RCSS'),
    ('CAL308', 'A321', 'RCKH', 'RJAA'), ('EVA872', 'B788', 'RCTP', 'ZSAM'),
    ('CXA8402', 'B738', 'ZSFZ', 'RCTP'), ('CSN3097', 'A320', 'ZSQZ', 'RCTP'),
    ('CAL126', 'A321', 'RCMQ', 'RJBB'), ('EVA265', 'A321', 'RCKH', 'VHHH'),
    ('UIA681', 'ATR7', 'RCYU', 'RCSS'), ('DAC7307', 'DH8D', 'RCGI', 'RCFN'),
    ('MDA502', 'ATR7', 'RCLY', 'RCFN'), ('CAL9821', 'B744', 'RCTP', 'RCKU'),
]
# ICAO flight levels in metres.  Domestic hops stay low; the cross-Strait and
# regional legs sit where the Shanghai ACC sectors above 7 800 m start to matter.
CRUISE_SHORT = [3050, 4270]          # FL100 / FL140
CRUISE_MED = [7010, 8230, 9140]      # FL230 / FL270 / FL300
CRUISE_LONG = [9750, 10360, 10970, 11580]   # FL320 / FL340 / FL360 / FL380


def demo_flights(t=None, n=None):
    """A deterministic pseudo-live picture; the whole fleet advances with time."""
    t = time.time() if t is None else t
    routes = _DEMO_ROUTES[:n] if n else _DEMO_ROUTES
    out = []
    for i, (cs, typ, dep, arr) in enumerate(routes):
        la1, lo1 = _AP[dep]; la2, lo2 = _AP[arr]
        total_nm = gc_distance_nm(la1, lo1, la2, lo2)
        period = max(total_nm / 460.0 * 3600.0, 1800.0)     # ~460 kt ground speed
        phase = ((t / period) + i * 0.137) % 1.0
        lat, lon = gc_point(la1, lo1, la2, lo2, phase)
        lat2, lon2 = gc_point(la1, lo1, la2, lo2, min(phase + 0.002, 1.0))
        cruise = (CRUISE_SHORT[i % 2] if total_nm < 300 else
                  CRUISE_MED[i % 3] if total_nm < 600 else CRUISE_LONG[i % 4])
        climb_f = min(120.0 / total_nm, 0.35)
        desc_f = 1.0 - min(150.0 / total_nm, 0.4)
        if phase < climb_f:
            alt = cruise * (phase / climb_f) ** 0.75
            vs = 1800
        elif phase > desc_f:
            alt = cruise * max(0.0, (1 - phase) / (1 - desc_f)) ** 0.9
            vs = -1600
        else:
            alt = cruise
            vs = 0
        out.append({
            'hex': 'DEMO%02d' % i, 'callsign': cs, 'registration': 'B-%04d' % (2000 + i * 7),
            'type': typ, 'lat': round(lat, 5), 'lon': round(lon, 5),
            'alt_m': round(alt, 0),
            'gs_kt': 460 if vs == 0 else 330, 'track': round(bearing(lat, lon, lat2, lon2), 0),
            'vs_fpm': vs, 'squawk': '%04d' % (2000 + i * 13 % 7000),
            'source': 'demo', 'demo': True,
            'dep': dep, 'arr': arr, 'dep_name': dep, 'arr_name': arr,
        })
    return out


def get_flights(mode='adsb.lol', want_routes=True):
    """mode: 'adsb.lol' | 'airplanes.live' | 'demo'.

    Returns (flights, notes, source).  An empty live answer is reported as a live
    answer, not a failure: community ADS-B coverage over inland China is thin and
    a genuine zero is useful information.  Only a transport failure falls back to
    the built-in demo fleet."""
    if mode == 'demo':
        return demo_flights(), ['示範資料 / demo data'], 'demo'
    fl, errs = fetch_live(mode)
    if errs and not fl:
        return demo_flights(), errs + ['無法取得實時資料，已切換為示範資料 / live feed '
                                       'unavailable, showing demo data'], 'demo'
    if fl and want_routes:
        errs += fetch_routes(fl, mode)
    if not fl:
        errs.append('連線正常，但此刻識別區內沒有被社群 ADS-B 收到的航班 / '
                    'feed reachable, no aircraft currently received in the zone')
    return fl, errs, mode
