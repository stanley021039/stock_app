# 台美股看盤 — Taiwan + US Stock Viewer

歷史股價瀏覽工具。資料來自 Yahoo Finance，存進本地 SQLite，前端用 React 看走勢圖。

```
stock_app\
├─ backend\            FastAPI + SQLite + yfinance
│  ├─ main.py          API 服務 (uvicorn 入口)
│  ├─ db.py            SQLite 存取層 (schema / upsert / 查詢)
│  ├─ fetch.py         yfinance 下載 + 正規化
│  ├─ tickers.py       內建的台美股代號清單 (種子)
│  ├─ init_db.py       一次性初始化 + 批次下載歷史
│  ├─ requirements.txt
│  └─ stock.db         SQLite 資料庫 (執行後產生)
└─ frontend\           React + Vite + lightweight-charts
   └─ src\
      ├─ pages\Home.jsx        首頁：指數卡片 + 選股
      ├─ pages\StockPage.jsx   個股頁：走勢圖 + 更新
      └─ components\PriceChart.jsx  K線/折線圖
```

## 技術選擇

| 層 | 技術 | 原因 |
|----|------|------|
| 後端 | **FastAPI** | 自動產生 API 文件 (`/docs`)、型別檢查、非同步 |
| 資料庫 | **SQLite** (純 `sqlite3`，無 ORM) | 單檔、零設定、足夠這種讀多寫少的場景 |
| 抓資料 | **yfinance 1.4.1** | ⚠️ 舊版 0.2.x 已對不上 Yahoo 新 API，必須用 1.x |
| 前端 | **React + Vite** | 元件化、生態大、HMR 開發快 |
| 圖表 | **lightweight-charts v5** (TradingView) | 專業金融圖、K線/折線/成交量、輕量 |

## 環境

Python 3.11 環境（conda 或 venv 皆可）。`start_*.bat` 會讀 `env.local.bat` 裡的 `STOCK_APP_PYTHON` 找 python：
把 `env.local.bat.example` 複製成 `env.local.bat` 並填入自己的路徑（這個檔不進 git）；沒有的話就用 PATH 上的 `python`。

以下指令都在專案根目錄執行，`python` 代表上述環境的 python。

```powershell
# 後端依賴 (已安裝；重建時用)
python -m pip install -r backend\requirements.txt
```

## 首次初始化資料

下載種子清單 (~84 檔：台美主要指數 + 權值股 + ETF) 的完整日線歷史：

```powershell
python backend\init_db.py
```

選項：
- `--force` 重抓全部（即使已有資料）
- `--only 2330.TW` 只抓指定代號（可重複）
- `--pause 0.6` 每檔間隔秒數（避免被 Yahoo 限流）

## 啟動

開兩個終端機（或用下方的 .bat）：

```powershell
# 1) 後端 (port 8000)
.\start_backend.bat

# 2) 前端 (port 5173)
.\start_frontend.bat
```

瀏覽器開 **http://localhost:5173** 。前端透過 Vite proxy 把 `/api` 轉到後端，無 CORS 問題。
API 文件：http://localhost:8000/docs

## 功能對應

1. **首頁預設顯示台美指數**：`home_indices` 資料表存清單，按「編輯」勾選增減（^TWII / ^GSPC / ^IXIC / ^DJI 預設）。
2. **選擇股票**：搜尋框 + 市場/類型篩選 + 清單表格。
3. **進到個股頁**：點卡片或表格列。
4. **預設 6 個月走勢**：個股頁開啟即套用 `6月`；指數用折線、個股/ETF 用 K線（可切換）。
5. **更新按鈕**：呼叫 `POST /api/symbols/{symbol}/update`，從資料庫最後一天起向 Yahoo 增量爬取並 upsert。

## 主要 API

| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/symbols?market=&type=&q=&with_quote=` | 代號清單 / 搜尋 |
| GET | `/api/symbols/{symbol}` | 單一代號詳情 + 最新報價 |
| GET | `/api/symbols/{symbol}/prices?range=6mo&interval=1d` | 區間價格。`interval=1d` 日線 (`1mo..max`)；`interval=5m` 5分線 (`1d,5d,1mo,max`) |
| POST | `/api/symbols/{symbol}/update?interval=1d` | 增量更新（更新按鈕用；`interval=5m` 更新 5 分線） |
| POST | `/api/symbols` | 新增追蹤代號並抓全歷史（首頁「＋新增股票」用） |
| POST | `/api/update-all` | 一鍵增量更新所有標的 |
| GET / PUT | `/api/home/indices` | 取得 / 設定首頁指數清單 |
| GET | `/api/backtest/strategies` | 列出可用回測策略 + 參數 |
| POST | `/api/backtest` | 執行回測（等權重投資組合 vs 大盤） |

## 日線 / 5分線切換

個股頁可在「日線」與「5分線」間切換：
- **日線**：完整歷史，存在 `prices` 表。區間 1月~全部。
- **5分線**：存在 `intraday_prices` 表（PK `symbol,interval,ts`，`ts` 為 epoch 秒）。區間 1日/5日/1月/60日。

> ⚠️ **Yahoo 對 5 分線只提供約 60 天**（1m≈7天、5m/15m/30m≈60天、1h≈2年、1d=全部）。所以 5 分線是「滾動 60 天」視窗，無法像日線往回拉好幾年。時間戳記用「交易所牆鐘時間當成 UTC」編碼，圖表才會顯示當地盤中時間（台股 09:00–13:30、美股 09:30–16:00）。

下載 5 分線（首次 / 重抓）：

```powershell
python backend\init_intraday.py            # 全部，5m，period=60d
python backend\init_intraday.py --interval 15m
python backend\init_intraday.py --only AAPL --force
```

個股頁的「⟳ 更新資料」按鈕會依目前是日線/5分線，分別做增量更新。

## 技術指標 (MA / KD)

個股頁的「技術指標」列可開關：
- **MA 5/20/60**：移動平均線，疊在價格上。
- **KD (9,3,3)**：台股式隨機指標，獨立子面板（K 橘、D 藍）。

指標在前端即時計算（`frontend/src/lib/indicators.js`），切換不需重抓資料。

## 回測 (Backtest tab)

頂部「回測」分頁。可選策略、自訂參數、選參與股票（等權重）、選大盤基準、設期間與本金，按「執行回測」會畫出 **投資組合 vs 大盤** 的權益曲線，並比較：總報酬、年化報酬 (CAGR)、年化波動、Sharpe、最大回撤、期末資產。

內建策略（`backend/backtest.py`）：
- `buy_hold` 買進持有
- `sma_cross` 均線交叉（快/慢線可調）
- `kd_cross` KD 黃金交叉
- `rsi_reversion` RSI 超賣進場

**擴充新策略**：在 `backtest.py` 寫一個用 `@strategy(key, name, params)` 裝飾的函式，回傳每日「部位」序列 (0~1)。前端會自動帶出新策略與其參數，無需改前端。例：

```python
@strategy("my_strat", "我的策略", [{"name": "win", "label": "視窗", "default": 10}])
def s_my_strat(df, p):
    # df: 日線 OHLCV (DatetimeIndex)；回傳 0/1 部位（記得 .shift(1) 避免未來函數）
    signal = df["close"] > sma(df["close"], int(p.get("win", 10)))
    return signal.astype(float).shift(1).fillna(0)
```

## 擴充到更多代號

目前是「指數 + 熱門股」的精選清單。要擴充：
- 單檔：前端尚未做新增 UI，可直接打 API：`POST /api/symbols {"symbol":"5483.TWO","name":"中美晶","type":"stock"}`
- 大量：把代號加進 `backend/tickers.py` 後重跑 `init_db.py`（已存在的會自動略過）。
- 全市場：台股可從證交所/櫃買中心的代號表灌入；美股可從交易所代號清單灌入。注意 Yahoo 有限流，建議加大 `--pause` 並分批跑。
