# -*- coding: utf-8 -*-
"""臺灣防空識別區航情圖 — Taiwan ADIZ traffic map (Streamlit).

Airspace, routes, significant points and aerodromes: AIP Taiwan (ais.caa.gov.tw)
ENR 5.2 / ENR 2.1 / ENR 4.4 / ENR 4.1 / AD 2.2.
ATC sector frequencies west of the Strait: AIP CHINA ENR 2.1.3 / 2.2.1.
Coastline: Natural Earth 1:10m, clipped and simplified (public domain).
Traffic: adsb.lol / airplanes.live community ADS-B, or the built-in demo fleet.

NOT FOR OPERATIONAL USE — research and training only.
"""
from __future__ import annotations
import time

import streamlit as st
import pydeck as pdk

import flights as FL
import layers_tw as LY
import tw_data as TW
from geoutil import fmt_level, fmt_dms

st.set_page_config(page_title='臺灣防空識別區航情圖 | Taiwan ADIZ Traffic',
                   page_icon='✈️', layout='wide', initial_sidebar_state='auto')

st.markdown("""
<style>
  .block-container{padding:.6rem .8rem 2rem;max-width:1600px}
  .hdr{display:flex;flex-wrap:wrap;gap:.4rem 1rem;align-items:baseline;margin-bottom:.35rem}
  .hdr .t{font-size:1.15rem;font-weight:650;letter-spacing:-.01em}
  .hdr .s{font-size:.78rem;opacity:.6;letter-spacing:.09em;text-transform:uppercase}
  .card{border:1px solid rgba(128,128,128,.28);border-radius:12px;padding:.7rem .85rem;
        margin-bottom:.55rem}
  .cs{font-size:1.45rem;font-weight:680;letter-spacing:-.01em;line-height:1.1;
      font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .route{display:flex;align-items:baseline;gap:.5rem;font-family:ui-monospace,monospace;
         font-size:1.15rem;font-weight:620;margin:.35rem 0 .15rem}
  .route .ar{opacity:.5;font-size:.9rem}
  .kv{display:grid;grid-template-columns:6.6rem 1fr;gap:.16rem .6rem;font-size:.83rem}
  .kv .k{opacity:.6}
  .freq{font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:680;line-height:1.15}
  .muted{opacity:.6;font-size:.76rem}
  .pill{display:inline-block;padding:.08rem .45rem;border-radius:999px;font-size:.7rem;
        border:1px solid currentColor;opacity:.85;margin-right:.3rem}
  @media (max-width:640px){.block-container{padding:.4rem .5rem 2rem}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_data():
    return TW.load()


NAV, SECTORS = load_data()
B = NAV['bbox']                                    # [west, south, east, north]

# --------------------------------------------------------------------------- #
#  Controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown('### 控制面板 Controls')

    st.markdown('**航班資料 Traffic**')
    src_label = {'adsb.lol': 'adsb.lol（實時 live）',
                 'airplanes.live': 'airplanes.live（實時 live）',
                 'demo': '示範資料 Demo（離線可用）'}
    source = st.selectbox('資料來源 Source', list(src_label), index=0,
                          format_func=lambda k: src_label[k])
    interval = st.select_slider('更新間隔 Interval (s)', [15, 30, 60, 120, 300], value=30)
    auto = st.toggle('自動更新 Auto-refresh', value=False,
                     help='更新期間介面不回應；長時間掛著建議用 streamlit-autorefresh')
    only_zone = st.toggle('只顯示識別區內 Only inside the ADIZ', value=False)
    show_gnd = st.toggle('顯示地面航機 On-ground traffic', value=True)

    st.markdown('---')
    st.markdown('**圖層 Layers**')
    basemap = st.radio('底圖 Basemap', ['vector', 'carto', 'none'], index=0, horizontal=True,
                       format_func=lambda k: {'vector': '向量海岸線', 'carto': 'CARTO 圖磚',
                                              'none': '無'}[k])
    theme = st.radio('配色 Theme', ['dark', 'light'], index=0, horizontal=True,
                     format_func=lambda k: {'dark': '深色', 'light': '淺色'}[k])
    show_awy = st.toggle('航路 Airways', value=True)
    show_wpt = st.toggle('航路點 Waypoints', value=False)
    show_apt = st.toggle('機場 Airports', value=True)
    show_adiz = st.toggle('防空識別區 ADIZ', value=True)
    show_fir = st.toggle('飛航情報區 Taipei FIR', value=True)
    show_lab = st.toggle('航機標籤 Aircraft labels', value=True)
    show_sec = st.toggle('管制扇區 ATC sectors（海峽西側）', value=False,
                         help='AIP CHINA 的扇區與頻率；台灣 AIP 不分扇區公布頻率')
    sec_level = None
    if show_sec:
        sec_level = st.select_slider(
            '扇區高度層 Sector level (m)',
            [0, 3000, 6000, 7800, 8400, 9200, 10000, 11000, 12500], value=9200,
            help='空域層層相疊，選一個高度層才看得出扇區邊界')

    st.markdown('---')
    st.caption('僅供研究與教學，不得用於實際飛行或空中交通服務。\n\n'
               'Research and training only — not for navigation or ATS.')

T = LY.THEME[theme]

# --------------------------------------------------------------------------- #
#  Traffic
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def traffic(mode, bucket):
    """`bucket` advances once per refresh interval, which is what expires this."""
    return FL.get_flights(mode)


with st.spinner('取得航班中 Fetching traffic…'):
    fl, notes, used = traffic(source, int(time.time() // interval))

pad = 1.0
fl = [f for f in fl
      if B[0] - pad <= f['lon'] <= B[2] + pad and B[1] - pad <= f['lat'] <= B[3] + pad]
if only_zone:
    fl = [f for f in fl if TW.in_adiz(NAV, f['lon'], f['lat'])]
if not show_gnd:
    fl = [f for f in fl if (f.get('alt_m') or 0) > 0]
fl.sort(key=lambda f: f['callsign'])

unit_of = {f['hex']: TW.controlling_unit(NAV, SECTORS, f['lon'], f['lat'], f.get('alt_m'))
           for f in fl}

# --------------------------------------------------------------------------- #
#  Header
# --------------------------------------------------------------------------- #
live = used != 'demo'
st.markdown(
    '<div class="hdr"><span class="t">臺灣防空識別區航情圖</span>'
    '<span class="s">Taiwan ADIZ Traffic</span>'
    '<span class="pill" style="color:%s">%s</span>'
    '<span class="pill">%d 架 aircraft</span></div>'
    % ('#3ecf8e' if live else '#f5b400',
       ('● 實時 LIVE · ' + used) if live else '● 示範資料 DEMO', len(fl)),
    unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
#  Layers
# --------------------------------------------------------------------------- #
layers = []

if basemap == 'vector':
    land_rows, fill, line = LY.land(NAV, T)
    layers.append(pdk.Layer('PolygonLayer', land_rows, get_polygon='polygon',
                            filled=True, stroked=True,
                            get_fill_color=fill + [255], get_line_color=line + [255],
                            line_width_units='pixels', line_width_min_pixels=0.6,
                            get_line_width=1, pickable=False))

if show_sec:
    rows = LY.sectors(SECTORS, T, sec_level)
    for r in rows:
        r['fill'] = list(r['colour']) + [38]
        r['line'] = list(r['colour']) + [175]
    layers.append(pdk.Layer('PolygonLayer', rows, get_polygon='polygon',
                            filled=True, stroked=True,
                            get_fill_color='fill', get_line_color='line',
                            line_width_units='pixels', line_width_min_pixels=1,
                            get_line_width=1, pickable=True, auto_highlight=True))

if show_awy:
    paths, awy_labels = LY.airways(NAV)
    layers.append(pdk.Layer('PathLayer', paths, get_path='path',
                            get_color=T['awy'] + [190], width_units='pixels',
                            get_width=1, width_min_pixels=1, pickable=True,
                            auto_highlight=True))
    layers.append(pdk.Layer('TextLayer', awy_labels, get_position='position',
                            get_text='text', get_size=10, size_units='pixels',
                            get_color=T['awy'] + [235], get_pixel_offset=[0, -7],
                            font_family='ui-monospace, monospace'))

if show_wpt:
    wpts = LY.waypoints(NAV)
    layers.append(pdk.Layer('ScatterplotLayer', wpts, get_position='position',
                            get_radius=2.2, radius_units='pixels',
                            get_fill_color=T['wpt'] + [220], pickable=True))

if show_apt:
    apts = LY.aerodromes(NAV)
    layers.append(pdk.Layer('ScatterplotLayer', apts, get_position='position',
                            get_radius=3.4, radius_units='pixels',
                            get_fill_color=T['apt'] + [240], pickable=True))
    layers.append(pdk.Layer('TextLayer', LY.labels(apts, 'icao'), get_position='position',
                            get_text='text', get_size=10, size_units='pixels',
                            get_color=T['apt'] + [240], get_pixel_offset=[0, -10],
                            font_family='ui-monospace, monospace'))

zone_rows = LY.zones(NAV, T, show_adiz, show_fir)
for r in zone_rows:
    r['line'] = list(r['colour']) + [235]
if zone_rows:
    layers.append(pdk.Layer('PolygonLayer', zone_rows, get_polygon='polygon',
                            filled=False, stroked=True, get_line_color='line',
                            line_width_units='pixels', get_line_width=1.6,
                            line_width_min_pixels=1.6, pickable=True))

# The selection survives reruns in session state; if that aircraft has since
# left the zone, fall back to the first one so the panel always has something.
sel_hex = st.session_state.get('sel_hex')
if fl and sel_hex not in {f['hex'] for f in fl}:
    sel_hex = fl[0]['hex']
ac_rows = LY.aircraft(fl, T, selected=sel_hex,
                      freq_of=lambda f: TW.freq_text(unit_of[f['hex']]))
if ac_rows:
    layers.append(pdk.Layer('IconLayer', ac_rows, get_icon='icon', get_position='position',
                            get_size='size', size_units='pixels', get_angle='angle',
                            get_color='colour', pickable=True, auto_highlight=True))
    if show_lab:
        layers.append(pdk.Layer('TextLayer', LY.labels(ac_rows), get_position='position',
                                get_text='text', get_size=10.5, size_units='pixels',
                                get_color=T['ink'] + [235], get_pixel_offset=[0, -16],
                                background=True,
                                get_background_color=T['ground'] + [150],
                                background_padding=[3, 1],
                                font_family='ui-monospace, monospace'))

view = pdk.ViewState(longitude=(B[0] + B[2]) / 2, latitude=(B[1] + B[3]) / 2,
                     zoom=5.4, pitch=0, bearing=0)
deck_args = dict(layers=layers, initial_view_state=view,
                 tooltip={'html': '{tip}',
                          'style': {'backgroundColor': '#0e151d', 'color': '#e8eef4',
                                    'border': '1px solid #233040', 'borderRadius': '8px',
                                    'padding': '8px 10px', 'fontSize': '12px'}})
if basemap == 'carto':
    # Style names differ slightly between pydeck releases; ask for the constant
    # and fall back to the literal the JSON API expects.
    want = 'CARTO_DARK_NO_LABELS' if theme == 'dark' else 'CARTO_LIGHT_NO_LABELS'
    deck_args['map_provider'] = 'carto'
    deck_args['map_style'] = getattr(getattr(pdk, 'map_styles', None), want, None) or (
        'dark_no_labels' if theme == 'dark' else 'light_no_labels')
else:
    deck_args['map_style'] = None

col_map, col_side = st.columns([3, 1], gap='small')

with col_map:
    st.pydeck_chart(pdk.Deck(**deck_args), height=620)
    st.markdown(
        '<div class="muted">海岸線 Natural Earth · 空域與航路 AIP Taiwan · '
        '扇區頻率 AIP CHINA%s</div>'
        % ('　·　圖磚 © OpenStreetMap © CARTO' if basemap == 'carto' else ''),
        unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
#  Flight panel
# --------------------------------------------------------------------------- #
with col_side:
    if not fl:
        st.info('此刻沒有航機可顯示。\n\nNo aircraft to show right now.')
    else:
        opts = [f['hex'] for f in fl]
        by_hex = {f['hex']: f for f in fl}
        idx = opts.index(sel_hex) if sel_hex in opts else 0
        chosen = st.selectbox('航班 Flight', opts, index=idx,
                              format_func=lambda h: '%s  %s' % (by_hex[h]['callsign'],
                                                                by_hex[h].get('type') or ''),
                              key='sel_hex')
        f = by_hex[chosen]
        u = unit_of[chosen]
        dep, arr = TW.airport_of(NAV, f.get('dep')), TW.airport_of(NAV, f.get('arr'))

        st.markdown(
            '<div class="card"><div class="cs">%s</div>'
            '<div class="muted">%s　%s　%s</div>'
            '<div class="route"><span>%s</span><span class="ar">→</span><span>%s</span></div>'
            '<div class="muted">%s</div>'
            '</div>'
            % (f['callsign'], f.get('type') or '—', f.get('registration') or '—',
               f['hex'].upper(),
               f.get('dep') or '—', f.get('arr') or '—',
               ' · '.join(x for x in [dep['name_zh'] if dep else (f.get('dep_name') or ''),
                                      arr['name_zh'] if arr else (f.get('arr_name') or '')]
                          if x) or '航線未知 route unknown'),
            unsafe_allow_html=True)

        vs = f.get('vs_fpm')
        st.markdown(
            '<div class="card"><div class="kv">'
            '<span class="k">高度 ALT</span><span>%s</span>'
            '<span class="k">地速 GS</span><span>%s kt</span>'
            '<span class="k">航向 TRK</span><span>%s°</span>'
            '<span class="k">升降 V/S</span><span>%s fpm</span>'
            '<span class="k">回應碼 SQ</span><span>%s</span>'
            '<span class="k">位置 POS</span><span>%s</span>'
            '</div></div>'
            % (fmt_level(f.get('alt_m')), f.get('gs_kt') or '—',
               int(f['track']) if f.get('track') is not None else '—',
               ('+%d' % vs) if isinstance(vs, (int, float)) and vs > 0 else (vs or '—'),
               f.get('squawk') or '—', fmt_dms(f['lon'], f['lat'])),
            unsafe_allow_html=True)

        if u['kind'] == 'sector':
            st.markdown(
                '<div class="card" style="border-left:3px solid #4f9ee0">'
                '<div class="freq">%s <span class="muted">MHz</span></div>'
                '<div>%s</div><div class="muted">%s　扇區 %s%s</div></div>'
                % (u['freq'] or '—', u['unit'], u['callsign'], u['detail'],
                   ('　備用 %s MHz' % u['sec']) if u['sec'] else ''),
                unsafe_allow_html=True)
        elif u['kind'] == 'fir':
            st.markdown(
                '<div class="card" style="border-left:3px solid #4f9ee0">'
                '<div class="freq">%s <span class="muted">MHz</span></div>'
                '<div>%s</div>'
                '<div class="muted">%s　緊急 %s</div>'
                '<div class="muted" style="margin-top:.3rem">公布頻率：%s</div>'
                '<div class="muted">AIP Taiwan 只公布整組頻率，不分扇區。</div></div>'
                % (u['freqs'][0], u['unit'], u['callsign'], u['emergency'],
                   '、'.join(u['freqs'])),
                unsafe_allow_html=True)
        else:
            st.markdown('<div class="card"><div class="muted">'
                        '不在臺北飛航情報區內，且無對應扇區。<br>'
                        'Outside the Taipei FIR with no matching sector.</div></div>',
                        unsafe_allow_html=True)

for n in notes:
    st.caption(n)

# --------------------------------------------------------------------------- #
#  Table
# --------------------------------------------------------------------------- #
with st.expander('航班清單 Flight list（%d）' % len(fl), expanded=False):
    st.dataframe(
        [{'呼號': f['callsign'], '機型': f.get('type') or '',
          '起 DEP': f.get('dep') or '', '訖 ARR': f.get('arr') or '',
          '高度': fmt_level(f.get('alt_m')), '地速 kt': f.get('gs_kt'),
          '航向': f.get('track'),
          '管制單位': unit_of[f['hex']].get('unit', '—'),
          '頻率': TW.freq_text(unit_of[f['hex']])} for f in fl],
        hide_index=True)

st.caption('資料來源：交通部民航局 AIP Taiwan（ENR 5.2 / ENR 2.1 / ENR 4.4 / ENR 4.1 / '
           'AD 2.2）· AIP CHINA ENR 2.1.3 / 2.2.1 · Natural Earth · '
           'adsb.lol / airplanes.live。航路的「點序」AIP 未公布，由最短路徑重建；'
           'M503、N884 等海峽西側航路不在台灣 AIP，未繪製。')

if auto:
    time.sleep(interval)
    st.rerun()
