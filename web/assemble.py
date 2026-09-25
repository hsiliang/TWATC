# -*- coding: utf-8 -*-
"""Assemble the Taiwan ADIZ traffic map: a standalone HTML file and the
Artifact body (same page without the wrapper the Artifact tool supplies)."""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
OUT = os.path.join(HERE, '..', 'dist')
os.makedirs(OUT, exist_ok=True)

nav = json.load(open(os.path.join(DATA, 'taiwan_navdata.json'), encoding='utf-8'))
# The ATC sectors that reach into the ADIZ box: the optional overlay, and the
# frequency lookup west of the Strait (AIP CHINA publishes sectorised
# frequencies, AIP Taiwan does not).
sectors = json.load(open(os.path.join(DATA, 'sectors_tw.json'), encoding='utf-8'))

payload = dict(nav)
payload['sectors'] = sectors
payload['waypoints'] = [{'name': w['name'], 'lat': w['lat'], 'lon': w['lon'],
                         'type': w['type'], 'facility': w['facility']}
                        for w in nav['waypoints']]

head = open(os.path.join(HERE, 'head.html'), encoding='utf-8').read()
body = open(os.path.join(HERE, 'body.html'), encoding='utf-8').read()
appjs = open(os.path.join(HERE, 'app.js'), encoding='utf-8').read()

REQUIRED = ['inRing', 'controllingUnit', 'basemapLayer', 'buildLayers', 'render',
            'paintPanel', 'select', 'fetchLive', 'fillRoutes', 'demoFlights',
            'refresh', 'safeRefresh', 'wire', 'schedule', 'clampView', 'projected',
            'ingest', 'tooltip', 'setFeed', 'showNote', 'adopt', 'jget', 'feedUrl',
            'planePolygon', 'scheduleRender', 'attribution', 'hitTest', 'viewport']
missing = [f for f in REQUIRED
           if ('function %s(' % f) not in appjs and ('%s = ' % f) not in appjs]
if missing:
    raise SystemExit('ERROR: called but never defined: %s' % missing)
# every container opened in the body must be closed: a stray </div> silently
# spills the settings sheet across the page, which is easy to miss in a diff.
_stack = []
for _close, _name in re.findall(r'<(/?)(div|aside|section|header)\b[^>]*>', body):
    if _close:
        if not _stack or _stack[-1] != _name:
            raise SystemExit('ERROR: body.html closes <%s> out of order' % _name)
        _stack.pop()
    else:
        _stack.append(_name)
if _stack:
    raise SystemExit('ERROR: body.html leaves %s unclosed' % _stack)

for ident in ('window.__TW_BOOT',):
    if ident not in appjs:
        raise SystemExit('ERROR: %s missing' % ident)

LOADER = """
<script>
(function () {
  var srcs = ['https://cdn.jsdelivr.net/npm/deck.gl@8.9.36/dist.min.js',
              'https://cdn.jsdelivr.net/npm/deck.gl@9.0.38/dist.min.js',
              'https://cdnjs.cloudflare.com/ajax/libs/deck.gl/8.8.27/deck.gl.min.js'];
  var i = 0;
  function go() { if (window.__TW_BOOT) window.__TW_BOOT(); }
  function next() {
    if (i >= srcs.length) { go(); return; }
    var s = document.createElement('script');
    s.src = srcs[i++]; s.onload = go; s.onerror = next;
    document.head.appendChild(s);
  }
  next();
})();
</script>
"""

data_tag = '<script>window.__TW__=%s;</script>' % json.dumps(
    payload, ensure_ascii=False, separators=(',', ':'))
app_tag = '<script>%s</script>' % appjs

artifact = head + '\n' + body + '\n' + data_tag + '\n' + app_tag + '\n' + LOADER
standalone = ('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width,initial-scale=1,'
              'viewport-fit=cover">\n' + head +
              '\n<style>html,body{height:100%}[hidden]{display:none!important}</style>\n'
              '</head>\n<body>\n' + body + '\n' + data_tag + '\n' + app_tag + '\n' +
              LOADER + '\n</body>\n</html>\n')

open(os.path.join(OUT, 'taiwan_adiz_traffic.html'), 'w', encoding='utf-8').write(standalone)
open(os.path.join(OUT, 'tw_artifact_body.html'), 'w', encoding='utf-8').write(artifact)

dom = set(re.findall(r'id="([^"]+)"', standalone))
js_ids = set(re.findall(r"el\('([^']+)'\)", appjs))
dangling = sorted(i for i in js_ids if i not in dom and i not in ('fp-x',))
print('sectors in view %d · waypoints %d · routes %d · aerodromes %d'
      % (len(sectors), len(payload['waypoints']), len(payload['routes']),
         len(payload['aerodromes'])))
print('dangling element ids:', dangling or 'none')
print('standalone %d KB · artifact %d KB · data %d KB'
      % (len(standalone.encode()) // 1024, len(artifact.encode()) // 1024,
         len(data_tag.encode()) // 1024))
