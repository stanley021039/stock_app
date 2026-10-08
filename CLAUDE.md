# CLAUDE.md

台美股看盤 — a Taiwan + US stock history viewer. Yahoo Finance → local SQLite →
FastAPI JSON API → React chart UI. See `README.md` for the user-facing feature
walkthrough; this file is the operational guide for working in the codebase.

## Environment & commands

- **The project's Python 3.11 env path is machine-specific and lives in
  `env.local.bat`** (gitignored; `STOCK_APP_PYTHON=...`, template in
  `env.local.bat.example`). Read it to find the env's `python.exe`; the
  `shioaji.exe` CLI is in that env's `Scripts\` folder. Below, `python` means
  that interpreter. Don't hardcode the path into tracked files.
- On the dev machine the system drive is almost full — never create envs or
  write large data there; keep them alongside the existing env. When passing
  Windows paths from the Bash tool, use **forward slashes** (the Bash tool eats
  backslashes). PowerShell handles backslashes fine.

```powershell
# install backend deps
python -m pip install -r backend\requirements.txt

# first-time / refresh data download (resumable; skips symbols that already have data)
python backend\init_db.py            # all seed tickers
python backend\init_db.py --only AAPL --force

# Taiwan index futures (台指期) — separate source (TAIFEX, not Yahoo)
python backend\init_taifex.py          # TX, resume from last stored
python backend\init_taifex.py --full   # TX from inception (1998)

# run servers (or double-click the .bat files)
start_backend.bat     # FastAPI on :8000  (uvicorn main:app --app-dir backend)
start_frontend.bat    # Vite on :5173     (npm run dev --prefix frontend)
```

Open http://localhost:5173. Vite proxies `/api` → `:8000`, so there are no CORS
issues in dev and the frontend always calls same-origin `/api/...`.
API docs: http://localhost:8000/docs

## Restarting after a code change

Backend and frontend both run as persistent Windows services (`StockAppBackend`,
`StockAppFrontend`) that Claude has no admin rights to control directly — the
user has to run the restart themselves. Whenever a change to `backend/*.py`
(or, less often, a frontend change that HMR isn't picking up) needs a restart
to take effect:

1. **Always state the exact restart command in chat**, e.g.:
   ```powershell
   net stop StockAppBackend
   net start StockAppBackend
   ```
   (swap in `StockAppFrontend` for a frontend restart.) Don't just say "please
   restart" — give the literal command every time, even if it was just given
   a few messages ago.
2. **Always follow up with an automated check that the restart actually
   landed** (e.g. a background Bash poll hitting an endpoint/behavior that
   only the new code would produce) rather than asking the user to confirm
   or assuming a "done" message means the new code is live. A restart can
   land on an older save than expected, or not happen at all — verify
   directly against the running process, not against what was said in chat.

## ⚠️ Gotcha: yfinance must be 1.4.1+

yfinance 0.2.x no longer works against Yahoo's current API (raises
`JSONDecodeError` even though raw HTTP to Yahoo succeeds). The project pins
`yfinance==1.4.1` (curl_cffi-based) in `backend/requirements.txt`. Don't downgrade.

## Architecture

**Backend** (`backend/`) — FastAPI + **plain `sqlite3` (no ORM)** + yfinance/pandas.
- `main.py` — all API routes + Pydantic models + CORS. Range strings
  (`1mo,3mo,6mo,1y,2y,3y,5y,10y,max`) map to a start date in `RANGE_DAYS`.
- `db.py` — SQLite layer. DB path is computed relative to `db.py`, so the server's
  CWD doesn't matter. Schema: `symbols` (has a `source` column, see routing below),
  `prices` (daily, PK `(symbol, date)`), `intraday_prices` (PK `(symbol, interval, ts)`,
  `ts` = epoch seconds), `home_indices`. `init_schema()` also runs a small in-place
  migration (`ALTER TABLE … ADD COLUMN source`). Writes use upsert
  (`INSERT … ON CONFLICT … DO UPDATE`).
- `fetch.py` — yfinance download + normalisation. `fetch_history` (daily) and
  `fetch_intraday` (5m etc.). Intraday rows are keyed by epoch `ts`: Yahoo's tz-aware
  index is converted to wall-clock-as-UTC so charts render local market time-of-day.
- `tickers.py` — the curated seed universe (~84). `init_db.py` seeds + bulk-downloads.
- `backtest.py` — strategy registry + engine + metrics (see below).
- `taifex.py` — Taiwan index futures (台指期) from the TAIFEX CSV download
  (Yahoo has no TW futures). Builds a **front-month continuous** series (most-traded
  regular-session contract per day; not back-adjusted, small gaps at rollover).
  CSV is `cp950`-encoded, **≤1 calendar month per request** (chunked monthly).

**Data-source routing**: `symbols.source` is `yahoo` (default) or `taifex`. The
daily-update paths (`/api/symbols/{s}/update`, `/api/update-all`) route through
`_fetch_daily_rows()` in `main.py` → yfinance or `taifex.fetch_daily()`. Futures
land in the same `prices` table; `symbols.type='future'`, `source='taifex'`,
and the symbol IS the TAIFEX commodity id (e.g. `TX`, `MTX`).

**Daily vs intraday**: the price + update endpoints take an `interval` param.
`interval=1d` reads/writes `prices`; `interval=5m` reads/writes `intraday_prices`
via `fetch_intraday`. Intraday is fetched **on demand** (the 5分線 toggle / update
button) — there's no bulk init script, and Yahoo only serves a rolling **~60-day**
window for 5m. TAIFEX is **daily only** (no intraday wired up).

**Frontend** (`frontend/src/`) — React 19 + Vite + react-router v7 + lightweight-charts **v5**.
- `api.js` — single fetch wrapper; all calls go through `/api`.
- `pages/Home.jsx` — index cards (editable), stock picker, add-stock UI, update-all.
- `pages/StockPage.jsx` — chart, range buttons (default `6mo`), 日線/5分線 toggle,
  MA/KD toggles, update. Unifies daily (`date`) and intraday (`time` epoch) bars into
  one `time` field before passing to the chart.
- `pages/Backtest.jsx` — strategy form (dynamic params), stock multi-select, results.
- `components/PriceChart.jsx` — candle/area + volume + MA overlays + KD sub-pane.
  `intraday` prop toggles `timeVisible` on the time axis; reads bars' `time` field.
- `components/EquityChart.jsx` — multi-line equity curves for the backtest.
- `lib/indicators.js` — MA + KD computed **client-side** (toggling doesn't refetch).

## Conventions

- **Yahoo symbols**: TWSE `2330.TW`, TPEx `5483.TWO`, US `AAPL`, indices `^TWII`,
  `^GSPC`. Symbols contain `.`/`^` — always `encodeURIComponent` in URLs (the api.js
  helper does this).
- **lightweight-charts v5 API**: series are added via `chart.addSeries(SeriesType, opts, paneIndex)`
  (e.g. `addSeries(CandlestickSeries, {...})`), not the v4 `addCandlestickSeries()`.
  KD uses `paneIndex=1` for a second pane. A series' `time` is a `YYYY-MM-DD` string
  for daily bars or a UNIX epoch (seconds) for intraday — StockPage normalises both
  into one `time` field. The `ResizeObserver` only re-applies width on a real change
  (guards against a scrollbar-driven feedback loop).
- Charts are recreated inside a `useEffect` keyed on their data/options; keep the
  dependency array a **constant length** (React errors on size changes — only seen
  transiently during HMR edits, harmless).
- Backend money/price types are `REAL`; volume is `INTEGER`; dates are text `YYYY-MM-DD`.

## ⚠️ 回測必須計入交易成本

**任何配對策略/回測的評估都必須扣掉交易成本。** 不計成本會得到相反的結論：
曾有一版機制在零成本下六對有三對改善，計入成本後六對全部退步。

台股實際費率（本專案採用的假設）：

| 項目 | 費率 | 收取時機 |
|---|---|---|
| 券商手續費 | 0.1425% × 0.2（2折）= **0.0285%** | 買、賣各收一次 |
| 證券交易稅 | **0.3%** | 只在賣出時收一次 |

```python
FEE, TAX = 0.001425 * 0.2, 0.003
LEAK = 1 - (1 - FEE - TAX) * (1 - FEE)     # = 0.3569% 每搬動一元的損耗
```

**對每次調倉的「搬動金額」課 `M * LEAK`，不是對總資產課費。** 因此
`turnover`（累計搬動金額 ÷ 起始資金）比交易次數更能預測成本侵蝕，兩者都要
記錄。範例：記憶體雙雄五年換手 147.8x → 光成本就吃掉約 0.53 倍起始資金。

尚未建模的成本：**滑價**（買賣價差、衝擊成本，以及回測假設「訊號與成交都在
同一日收盤價」，實務上得掛收盤集合競價、無法保證成交在該價位）。現有數字
因此仍偏樂觀。

## 評估指標：用 IR 與倍數比，不要用 Sharpe 與 pp

- **倍數比** = 策略終值 ÷ 買進持有終值。優於「超額pp」，因為 pp 會被基期
  報酬的複利放大（同一組數據下 pp 差 2.65 倍、倍數比只差 1.35 倍）。
- **IR**（Information Ratio）= 年化的「策略日報酬 − B&H日報酬」風險調整值。
  優於 Sharpe，因為 Sharpe 量到的大半是兩檔股票本身共有的 beta 波動（策略與
  benchmark 同樣承受），不是策略的優劣。判讀：>1.0 頂尖、0.6~1.0 很好、
  0.4~0.6 好、<0.4 普通。
- **End勝率**（每個歷史日當起點、抱到資料結束，勝過 B&H 的比例）是主要篩選
  門檻，**≥85%** 才納入。**1年滾動勝率**為輔助參考。
- 新股對必看：**長 MA 區間是否為正**。若 MA30/60/90 全為負 IR，代表兩檔沒有
  季度級的均值回歸關係（結構性不適配），不是參數沒調好。已知失敗案例：
  台燿/聯茂（全格負）、台達電/光寶科（長MA全負）、華星光/聯鈞（64格全負）。

## 配對再平衡策略（三個並行的 tab）

- `backend/pair_strategy.py` (v1, `/pair-strategy`)：正式版。rolling MA 偏離、
  6級階梯、每級賣30%。目前六對：記憶體、封測、被動元件、功率元件、
  AI伺服器（緯創/緯穎）、航運（長榮/陽明）。`EXCLUDED` dict 保留評估過但
  未採用的股對與原因。
- `backend/pair_strategy_v2.py` (`/pair-strategy-v2`)：research 用。改用
  start_baseline 偏離（今日 vs 視窗中最舊 k 天的均價），偏動量而非均值回歸。
  仍是原本四對、舊指標。
- `backend/pair_strategy_lite.py` (`/pair-strategy-lite`)：資金縮減版，2級。
  **機制正在改版中，規格見 `backend/LITE_MECHANISM_SPEC.md`**，參數見
  `backend/LITE_PARAMS.txt`。

三者共用前端元件 `frontend/src/components/PairStrategyShared.jsx`
（`ThresholdBar` / `SignalRow` / `InfoIcon`），改動時務必確認不會弄壞其他 tab。
只有 v1 有 `/update` endpoint，v2 與 lite 共用它（監看的標的相同）。

**Yahoo 代號陷阱**：上櫃股要用 `.TWO` 不是 `.TW`（例：台燿 `6274.TWO`、
上詮 `3363.TWO`），用錯會回 404。加新標的前先用 `fetch.fetch_history` 兩種
後綴都試一次。

## Extending the backtest (designed to be extended)

Add a strategy in `backend/backtest.py` — the frontend renders it automatically
(it reads `GET /api/backtest/strategies`). A strategy returns a daily **position**
series (0..1 = fraction invested); `.shift(1)` it to avoid look-ahead.

```python
@strategy("my_strat", "我的策略", [{"name": "win", "label": "視窗", "default": 10}])
def s_my_strat(df, p):                     # df: OHLCV, DatetimeIndex
    signal = df["close"] > sma(df["close"], int(p.get("win", 10)))
    return signal.astype(float).shift(1).fillna(0)
```

The engine turns positions → daily returns → equity curve, builds an equal-weight
portfolio across the selected symbols, and compares it to the benchmark
(buy & hold). Metrics: total return, CAGR, annualised vol, Sharpe, max drawdown.

## Verifying changes

Backend + Vite dev servers are the way to verify. After editing previewable code,
load http://localhost:5173, check the browser console for errors, and exercise the
affected page. Backend logic (fetch/backtest) can be smoke-tested directly:
`python backend\init_db.py --only <SYM> --force` (the env's python, see above).
