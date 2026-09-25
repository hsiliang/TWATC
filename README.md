# 臺灣防空識別區航情圖 · Taiwan ADIZ Traffic Map

即時航情圖，範圍限定在臺灣防空識別區：**高空航路**、**機場**、**防空識別區與臺北飛航情報區邊界**、
海峽西側的**管制扇區與頻率**。點選任何一架航機，會依它的位置與高度算出正在管它的單位與頻率。

A live traffic map bounded to the Taiwan ADIZ: upper airways, aerodromes, the
ADIZ and Taipei FIR boundaries, and the ATC sectors west of the Strait. Click any
aircraft and the map works out which unit is controlling it, on what frequency,
from its position and level.

兩個前端共用同一份資料與同一套判斷規則：

| | 適合 | 實時航班來源 |
|---|---|---|
| **`web/`** 單檔 HTML | 丟到任何靜態空間、直接用瀏覽器打開、離線可用 | ADS-B Exchange（RapidAPI 金鑰，只存在瀏覽器裡） |
| **`streamlit/`** Streamlit | 部署到 Streamlit Community Cloud、桌面使用 | adsb.lol／airplanes.live（**免金鑰**） |

為什麼兩邊來源不同：瀏覽器直接發請求會被 CORS 擋，免費的社群 ADS-B 來源大多不送
`Access-Control-Allow-Origin`；Streamlit 是伺服器端取資料，沒有這道牆。兩邊取不到資料時
都會自動退回內建的示範航班，介面不會空掉。

---

## 快速開始 Quick start

**單檔 HTML** — 什麼都不用裝：

```bash
open dist/taiwan_adiz_traffic.html        # macOS；Linux 用 xdg-open
```

**Streamlit**：

```bash
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

**重建**（改了 `tools/navdata_raw.json` 之後）：

```bash
cd tools && python3 build_tw.py           # → data/taiwan_navdata.json
cd ../web && python3 assemble.py          # → dist/taiwan_adiz_traffic.html
```

---

## 資料 Data

`data/taiwan_navdata.json` 由 `tools/build_tw.py` 產生，來源是交通部民航局 eAIP，
版本 `AIRAC AIP AMDT 03-26`（2026-08-06 生效）。

| 內容 | 數量 | 出處 |
|---|---|---|
| 防空識別區邊界 | 6 點 | AIP Taiwan **ENR 5.2** |
| 臺北飛航情報區邊界 | 6 點 | AIP Taiwan **ENR 2.1** |
| 航路點與助航設施 | 175 | AIP Taiwan **ENR 4.4 / ENR 4.1** |
| 高空航路 | 20 條 | AIP Taiwan **ENR 4.4** |
| 機場 ARP | 19 座（臺灣全部）＋ 6 座大陸沿海參考點 | AIP Taiwan **AD 2.2** |
| 管制單位與頻率（臺灣） | 臺北區管、臺北／高雄近場 | AIP Taiwan **ENR 2.1** |
| 管制扇區與頻率（海峽西側） | 32 個進入識別區的扇區 | AIP CHINA **ENR 2.1.3 / 2.2.1** |
| 海岸線 | 119 環 / 3208 點 | Natural Earth 1:10m（公有領域） |

**防空識別區的實際範圍**不是常見的 21–26N 方框，而是：

```
21N/117.5E → 21N/121.5E → 22.5N/123E → 29N/123E → 29N/117.5E
```

臺北飛航情報區的東界到 124E、切角在 23.5N；西、南、北界與識別區相同。

### 三個必須講清楚的限制

1. **航路的點序是重建出來的。** AIP Taiwan 的 ENR 3.1／3.2 是 NIL，只公布航路點的
   「歸屬」（ENR 4.4）而不公布順序。程式以最短開放路徑重建，20 條裡有 18 條近乎共線
   （繞行比 ≤ 1.07）；**R596 與 W2 的繞行比 1.22，信心較低**，UI 上有標註。
2. **M503、N884、A470 沒有畫。** 這些是海峽西側的大陸航路，臺灣 AIP 未公布，也找不到
   公開座標，寧可留白也不猜。這是本圖最大的一塊缺口。
3. **臺灣上空沒有逐扇區頻率。** AIP Taiwan 只公布每個管制單位的整組頻率，所以識別區
   東半部顯示的是「TAIPEI CONTROL ＋ 公布頻率清單」；逐扇區頻率只在海峽西側才有
   （來自 AIP CHINA）。

### 頻率判斷規則

進場／終端管制優先於區域管制，同層級時面積小者優先——這正是 AIP 裡那些「Exclude …」
註記的實際行為。公布的上限**含**本數，標 `(exclusive)` 的界線**不含**。高度一律換算成
公尺的標準氣壓高度（QNE）再比對，與 AIP 的公制高度層一致。

---

## 幾個實作上的決定

**航機不是圖示，是幾何。** deck.gl 的 `IconLayer` 得先把圖示抓進來（即使是 `data:` URL
也要走 `fetch()`），在受限的嵌入環境裡會被擋掉，結果就是其他圖層都在、只有航機不見。
單檔 HTML 版因此改用 `PolygonLayer`：飛機輪廓存在單位正方形裡，依目前 zoom 換算成
經緯度，完全不需要材質。Streamlit 版跑在一般網頁上沒有這個限制，用內嵌 PNG 的
`IconLayer` 即可。

**海岸線內建在頁面裡。** 光柵圖磚同樣要連外，被擋就只剩一片黑。`tools/clip_land.py`
把 Natural Earth 1:10m 裁到視窗範圍、Douglas–Peucker 簡化到約 170 公尺，59 KB，
不連線也看得到臺灣、澎湖、金馬、綠島蘭嶼與福建沿岸。圖磚仍保留為選項。

**點擊命中自己算。** deck.gl 靠回讀著色後的畫面來 picking，這個回讀在某些嵌入環境裡
回來是空的（實測掃過整個畫布連航路、機場都挑不到）。航機數量不多、座標本來就在手上，
所以 `hitTest()` 直接把航機投影到螢幕座標取最近的一架，哪裡都能用。

**兩次更新之間會推估外插。** 依航向與地速推算位置，最多 120 秒，讓航機平滑移動而不是
每次更新跳一格。

---

## 檔案 Layout

```
data/     taiwan_navdata.json  航路、航路點、機場、邊界、海岸線
          sectors_tw.json      進入識別區的 AIP CHINA 扇區
tools/    build_tw.py          navdata_raw.json + land_tw.json → taiwan_navdata.json
          navdata_raw.json     逐筆抄錄的 AIP 原始值（AIP 改版時只改這裡）
          clip_land.py         Natural Earth 裁切與簡化
web/      head.html body.html app.js
          assemble.py          注入資料 → dist/taiwan_adiz_traffic.html
                               建置守衛：必要函式、懸空的元素 id、body 標籤配對
streamlit/app.py layers_tw.py tw_data.py flights.py geoutil.py assets.py
dist/     taiwan_adiz_traffic.html   建好的單檔版，直接打開就能用
```

海岸線要重做時，先取 Natural Earth 的 `ne_10m_land.geojson` 與
`ne_10m_minor_islands.geojson`（`raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/`），
放在 `tools/` 下執行 `python3 clip_land.py`。

---

## 授權 Licence

程式碼採 MIT（見 `LICENSE`）。

資料另計：航路、航路點、機場、邊界與頻率抄自 **AIP Taiwan**（交通部民航局）與
**AIP CHINA**（中國民用航空局），著作權屬各該機關，此處僅為研究與教學目的引用，
並非官方版本、也不保證與現行版本一致。海岸線來自
**Natural Earth**（公有領域）。實時航班由 **adsb.lol**、**airplanes.live**、
**ADS-B Exchange** 提供，各自的使用條款以其網站為準。

## 免責 Disclaimer

**僅供研究與教學，不得用於實際飛行、簽派或空中交通服務。**
社群 ADS-B 的涵蓋範圍不均，海上與低空常有缺漏；顯示的頻率是依公布資料推算的結果，
不是當下的實際指派。航路的點序是重建的，不是官方公布的順序。

**Research and training only — not for navigation, dispatch, or air traffic
services.** Community ADS-B coverage is uneven, the frequency shown is derived
from published data rather than the assignment actually in force, and route point
order is reconstructed, not official.
