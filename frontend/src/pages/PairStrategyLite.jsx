import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { NEXT_DAY, InfoIcon, ThresholdBar, ThresholdBarCaption, BAR_W } from '../components/PairStrategyShared.jsx'
import { levelChangeLabel, TriggerList } from '../components/LiteTriggers.jsx'

const fmtPrice = (x) => (x == null ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: 2 }))
const fmtChangePct = (x) => (x == null ? '' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}%`)
const changeCls = (x) => (x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat')

// Same tab format as PairStrategy.jsx (v1) -- same rolling-MA dev/diff
// formula, same MA windows and tier thresholds -- but a different capital-
// movement rule: a 3-position state machine (50/50 -> 75/25 -> 100/0) with
// an asymmetric entry/exit rule instead of v1's tiered ratchet. See
// backend/pair_strategy_lite.py's docstring and LITE_MECHANISM_SPEC.md for
// the mechanism. Reuses v1's update endpoint since it watches the same
// symbols.
const LIVE_POLL_MS = 15000
const LIVE_POLL_MS_CLOSED = 5 * 60 * 1000 // market closed: check back every 5min instead

export default function PairStrategyLite() {
  const [config, setConfig] = useState(null)
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState(NEXT_DAY)
  const [signals, setSignals] = useState(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [notice, setNotice] = useState(null)
  const [dateWarning, setDateWarning] = useState(null)
  const [error, setError] = useState(null)
  const [updatePopup, setUpdatePopup] = useState(null)

  const [liveResults, setLiveResults] = useState([])
  const [quoteServiceOk, setQuoteServiceOk] = useState(true)
  const [liveCheckedAt, setLiveCheckedAt] = useState(null)
  const [quotes, setQuotes] = useState({})
  const [indexQuotes, setIndexQuotes] = useState({})
  const [trackedSymbols, setTrackedSymbols] = useState(new Set())
  const [overrides, setOverrides] = useState({})

  // Read by the self-scheduling live-poll effect below, which has an empty
  // dependency array (so it can freely reschedule itself without tearing
  // down and losing its timer) -- a ref sidesteps that effect's closure
  // otherwise being stuck with whatever selectedDate was on mount.
  const selectedDateRef = useRef(selectedDate)
  useEffect(() => { selectedDateRef.current = selectedDate }, [selectedDate])

  function refreshQuotes(date) {
    api.getPairStrategyLiteQuotes(date).then(setQuotes).catch((e) => setError(e.message))
  }

  function refreshIndexQuotes(date) {
    api.getPairStrategyLiteIndexQuotes(date).then(setIndexQuotes).catch((e) => setError(e.message))
  }

  function refreshTrackedSymbols() {
    return api.getTrackedSymbols()
      .then((rows) => setTrackedSymbols(new Set(rows.map((r) => r.symbol))))
      .catch((e) => setError(e.message))
  }

  function refreshOverrides() {
    return api.getPairStrategyLiteOverrides().then(setOverrides).catch((e) => setError(e.message))
  }

  // The displayed position normally comes straight from the computed
  // signal (s.entries_since_reset, signed by which side s.basis_diff is
  // currently tilted toward), but the user's *real* holdings can drift
  // from that -- a manual trade outside the app, a partial fill, deciding
  // not to follow a signal, etc. `position` folds level+side into one
  // signed integer -2..2 (negative = A strong/tilt-to-A, positive = B
  // strong/tilt-to-B, matching diff's own sign convention and therefore
  // the bar's own left-right axis) so "one step left/right" is a single,
  // unambiguous move including through zero.
  //
  // Reaching position 0 via the arrows still PUTs an explicit {level:0,
  // side:0} override rather than clearing it -- clearing means "trust the
  // computed signal", which is a different thing and can immediately jump
  // back to a nonzero level if that's what the price data currently says.
  // Only the explicit "恢復自動" button clears the override.
  function currentPosition(s, override) {
    if (override) return override.level * override.side
    const level = s.entries_since_reset
    if (level === 0) return 0
    return level * (s.basis_diff >= 0 ? 1 : -1)
  }

  async function adjustPosition(pairKey, s, override, delta) {
    const base = currentPosition(s, override)
    const next = Math.min(2, Math.max(-2, base + delta))
    if (next === base) return
    const level = Math.abs(next)
    const side = level === 0 ? 0 : (next > 0 ? 1 : -1)
    try {
      await api.setPairStrategyLiteOverride(pairKey, level, side)
      await refreshOverrides()
      await refreshLive() // re-check right away -- don't wait for the next scheduled poll
    } catch (e) {
      setError(e.message)
    }
  }

  async function resetOverride(pairKey) {
    try {
      await api.clearPairStrategyLiteOverride(pairKey)
      await refreshOverrides()
      await refreshLive()
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    ;(async () => {
      try {
        const [cfg, d] = await Promise.all([api.getPairStrategyLiteConfig(), api.getPairStrategyLiteDates()])
        setConfig(cfg)
        setDates(d.dates)
      } catch (e) {
        setError(e.message)
      }
    })()
    refreshTrackedSymbols()
    refreshOverrides()
  }, [])

  // Quotes must follow whichever date is being browsed -- not always
  // "latest" -- otherwise switching to a past date still shows today's
  // price next to each symbol instead of that day's own close.
  useEffect(() => {
    refreshQuotes(selectedDate === NEXT_DAY ? undefined : selectedDate)
    refreshIndexQuotes(selectedDate === NEXT_DAY ? undefined : selectedDate)
  }, [selectedDate])

  const [marketOpen, setMarketOpen] = useState(true)

  // Also refreshes quotes on the same cadence -- without this, the yellow
  // live-diff marker (fed by liveResults, set right below) visibly moves
  // every 15s while each side's own price/漲跌幅 (fed by `quotes`, which
  // used to only ever refetch on mount or a date change) just sits frozen
  // until the page is manually reloaded, even though both are supposed to
  // be the same live/tracked price. Skipped while browsing a specific past
  // date -- that quote is that date's own close, not "latest", and has no
  // business moving on a timer.
  //
  // Pulled out of the poll effect so adjustPosition/resetOverride can call
  // it directly too -- adjusting the override should re-check "does this
  // now need a notification" immediately, not sit stale until whatever's
  // left of the current 15s cycle runs out.
  async function refreshLive() {
    try {
      const r = await api.getPairStrategyLiteLive()
      setLiveResults(r.results)
      setQuoteServiceOk(r.quote_service_ok)
      setMarketOpen(r.market_open)
      if (r.checked_at) setLiveCheckedAt(r.checked_at)
      if (selectedDateRef.current === NEXT_DAY) {
        refreshQuotes()
        refreshIndexQuotes()
      }
      return r.market_open
    } catch {
      setQuoteServiceOk(false)
      return true
    }
  }

  // Self-scheduling instead of setInterval: once the backend says the
  // market's closed (it already skips calling the quote service in that
  // case -- see main.py's _tse_market_open), fall back to a slow check so
  // a tab left open overnight isn't hammering even our own backend every
  // 15s for nothing.
  useEffect(() => {
    let cancelled = false
    let timer = null
    async function poll() {
      const stillOpen = await refreshLive()
      if (!cancelled) timer = setTimeout(poll, stillOpen ? LIVE_POLL_MS : LIVE_POLL_MS_CLOSED)
    }
    poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  const liveByKey = Object.fromEntries(liveResults.map((r) => [r.key, r]))

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .getPairStrategyLiteSignals(selectedDate === NEXT_DAY ? undefined : selectedDate)
      .then((r) => setSignals(r.signals))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedDate])

  async function handleUpdate() {
    setUpdating(true)
    setNotice(null)
    setDateWarning(null)
    setError(null)
    try {
      const r = await api.updatePairStrategy()
      if (!r.updated) {
        if (r.reason === 'weekend') setNotice('今天是週末，非交易日')
        else if (r.reason === 'market not closed yet (13:30 Taipei)') setNotice('今天還沒收盤（13:30前），暫不更新')
      } else {
        const d = await api.getPairStrategyLiteDates()
        setDates(d.dates)
        setSelectedDate(NEXT_DAY)
        refreshQuotes()
        showUpdatePopup(`已更新 ${r.succeeded}/${r.attempted}`)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setUpdating(false)
    }
  }

  function showUpdatePopup(text) {
    setUpdatePopup(text)
    setTimeout(() => setUpdatePopup(null), 5000)
  }

  const dateSet = new Set(dates)
  const minDate = dates[dates.length - 1]
  const maxDate = dates[0]

  function handleDateInput(value) {
    setDateWarning(null)
    if (!value) {
      setSelectedDate(NEXT_DAY)
      return
    }
    if (!dateSet.has(value)) {
      setDateWarning(`${value} 不是交易日，或超出可查詢範圍（最近${dates.length}個交易日：${minDate}～${maxDate}），請重新選擇`)
      return
    }
    setSelectedDate(value)
  }

  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
    <div style={{ flex: 1, minWidth: 0 }}>
      {updatePopup && (
        <div
          style={{
            position: 'fixed', top: 70, right: 24, zIndex: 100,
            background: 'var(--panel-2)', border: '1px solid var(--accent)', borderRadius: 8,
            padding: '10px 16px', fontSize: 13, boxShadow: '0 4px 16px rgba(0,0,0,.5)',
          }}
        >
          {updatePopup}
        </div>
      )}

      <div className="section-title">
        <h2>配對再平衡策略（資金縮減版）</h2>
      </div>

      <div className="editor" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
              <button className="active" onClick={handleUpdate} disabled={updating}>
                {updating ? '更新中…' : '⟳ 更新'}
              </button>
              <button className={selectedDate === NEXT_DAY ? 'active' : ''} onClick={() => handleDateInput('')}>即時</button>

              <label style={{ color: 'var(--muted)', fontSize: 13 }}>日期</label>
              <input
                type="date"
                value={selectedDate === NEXT_DAY ? '' : selectedDate}
                min={minDate}
                max={maxDate}
                onChange={(e) => handleDateInput(e.target.value)}
              />

              {loading && <span style={{ color: 'var(--muted)', fontSize: 13 }}>載入中…</span>}
              {notice && <span className="toast">{notice}</span>}
              {dateWarning && <span className="toast err">{dateWarning}</span>}
              {error && <span className="toast err">{error}</span>}
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8, lineHeight: 1.8 }}>
              <div><b>更新</b>：14:00後下載yfinance今日收盤價</div>
              <div><b>即時</b>：切換至當前日期</div>
              <div>*可到<Link to="/tracked-symbols">報價追蹤</Link>頁面管理追蹤標的；黃色股票名稱代表該檔正在追蹤中。</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 24, flexShrink: 0 }}>
            <IndexQuoteCard label="台股加權指數" quote={indexQuotes.twii} />
            <IndexQuoteCard label="0050" quote={indexQuotes.yuanta50} />
          </div>
        </div>
      </div>

      {!quoteServiceOk && (
        <div className="toast err" style={{ marginBottom: 12 }}>
          即時報價服務連不上，「今日即時觸發」暫時無法更新（不影響其他功能）
        </div>
      )}

      {signals && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>A標的</th>
                <th>訊號區間(A-B)</th>
                <th>B標的</th>
                <th>當日實際結果</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <LiteSignalRow
                  key={s.key}
                  s={s}
                  trackedA={trackedSymbols.has(s.symA)}
                  trackedB={trackedSymbols.has(s.symB)}
                  live={liveByKey[s.key]}
                  quoteA={quotes[s.symA]}
                  quoteB={quotes[s.symB]}
                  override={overrides[s.key]}
                  onAdjustPosition={(delta) => adjustPosition(s.key, s, overrides[s.key], delta)}
                  onResetOverride={() => resetOverride(s.key)}
                />
              ))}
            </tbody>
          </table>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
            {marketOpen
              ? `兩檔標的都在追蹤名單裡的股對，每 ${LIVE_POLL_MS / 1000} 秒會重新算一次是否已觸發加碼/回流`
              : '現在非台股交易時間(平日09:00-13:30)，暫停即時報價輪詢'}
            {liveCheckedAt && `（最後檢查：${liveCheckedAt}）`}。
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
            數線說明：每一級門檻都各自標一個刻度——紅側＝A是弱勢股（往A加碼）、綠側＝B是弱勢股，粗刻度是再往外一級的門檻，
            淡色刻度是目前所在級別以內、已經穿越過的門檻（滑鼠移到刻度上可看該級的細節；<b>外層門檻(T2)只進不退</b>，
            退回內層門檻(T1)是唯一的部分退場，退回內層之後就黏著，只有翻正負號才會整個回到50/50）；
            亮色豎線＝目前A-B差值所在位置；橙色刻度＋色帶＝回到50/50的門檻(diff=0)，色帶長度是「目前位置離50/50還有多遠」，
            只有目前不是50/50時才會出現；黃色刻度＝有追蹤的股對用即時報價算出來的當下位置，隨每次輪詢更新。
          </div>
        </div>
      )}

      <div style={{ marginTop: 40, borderTop: '1px solid var(--border)', paddingTop: 20 }}>
        <h3 style={{ marginBottom: 8 }}>策略詳情</h3>
        <div style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.7 }}>
          <p>
            訊號算法：<code>dev_X(t) = 收盤價_X(t) / MA_X(t) − 1</code>，<code>diff(t) = dev_A(t) − dev_B(t)</code>；
            diff&gt;0 代表A是強勢股（賣A買B），diff&lt;0 則反過來。
          </p>
          <p>
            <b>三段式配置</b>（50/50 → 75/25 → 100/0，數字是弱勢股權重），進場、退場門檻不對稱：
          </p>
          <ul style={{ marginTop: -8 }}>
            <li>漲破 T1：50/50 → 75/25</li>
            <li>漲破 T2：→ 100/0</li>
            <li><b>跌破 T2 維持 100/0 不動</b>（外層門檻只進不退，消滅邊緣來回換手）</li>
            <li>從100/0跌破 T1：退到 75/25，之後黏著（<b>減碼只有一次</b>）</li>
            <li>diff 翻正負號：強制回到 50/50，若當下 |diff| 已經超過門檻，同一天直接進場到對應級別</li>
          </ul>
          <p>
            <b>已知狀況</b>：記憶體雙雄的 IR、1年勝率是六對中最高的；其餘幾對還有優化空間。
            目前 T1/T2 門檻值是沿用舊參數，還沒針對這個機制重新網格搜索——這是後續最該做的優化。
          </p>

          {config && (
            <div style={{ overflowX: 'auto', margin: '12px 0' }}>
              <table>
                <thead>
                  <tr>
                    <th>股對</th>
                    <th>MA</th>
                    <th>門檻(T1/T2)</th>
                    <th style={{ textAlign: 'right' }}>倍數比</th>
                    <th style={{ textAlign: 'right' }}>IR</th>
                    <th style={{ textAlign: 'right' }}>End勝率</th>
                    <th style={{ textAlign: 'right' }}>1年勝率</th>
                    <th style={{ textAlign: 'right' }}>超額pp</th>
                    <th style={{ textAlign: 'right' }}>最大回撤</th>
                    <th style={{ textAlign: 'right' }}>換手</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(config.pairs).map(([key, p]) => (
                    <tr key={key}>
                      <td>{p.label}({p.nameA}/{p.nameB})</td>
                      <td>{p.ma}</td>
                      <td>{p.tiers.map((t) => (t * 100).toFixed(1)).join('/')}% (弱勢股權重 {p.band_weights.map((w) => (w * 100).toFixed(0)).join('/')}%)</td>
                      <td style={{ textAlign: 'right' }}>{p.bh_ratio.toFixed(2)}x</td>
                      <td style={{ textAlign: 'right' }}>{p.ir.toFixed(2)}</td>
                      <td style={{ textAlign: 'right' }}>{p.end_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.one_year_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.excess_pp >= 0 ? '+' : ''}{p.excess_pp.toFixed(1)}</td>
                      <td style={{ textAlign: 'right' }}>{p.max_dd.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.turnover.toFixed(1)}x</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>
                以上回測數字皆已計入台股實際交易成本（手續費0.0285%×買賣各一次 + 證交稅0.3%僅賣出收取）；
                換手＝回測期間累計搬動金額 ÷ 起始資金，是成本侵蝕的主要驅動因素，比交易次數更值得留意。
              </div>
            </div>
          )}
          <p>
            重要提醒：這是<b>資金不足以分6筆進場</b>時的簡化版本，只需要3段配置就能運作；
            門檻值還沒針對這個機制重新最佳化，實際使用時請留意。
          </p>
        </div>
      </div>
    </div>

    <div style={{ width: 240, flexShrink: 0, position: 'sticky', top: 70 }}>
      <div className="editor" style={{ marginBottom: 0 }}>
        <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 6 }}>今日觸發訊號</div>
        <TriggerList liveResults={liveResults} />
      </div>
    </div>
    </div>
  )
}

// Price shown next to each side's name. `live` only ever has a value when
// the backend actually computed one (both symbols tracked, market open,
// today's row ready -- see main.py's /pair-strategy-lite/live), so its
// quote (from /quotes) carries is_final straight from the prices row
// itself now -- close/live_price are mutually exclusive (exactly one is
// non-null) and is_final says which, so the label follows directly from
// the DB's own state instead of guessing from browsingHistory or cross-
// referencing the separate /live poll. A tracked symbol still mid-session
// (is_final=false) shows its live price + quote_time; once settled (a
// past date, or today after close/update) it shows the real close.
function sidePrice(quote) {
  if (!quote) return { price: null, changePct: null, label: '', quoteTime: null }
  if (quote.is_final) {
    return { price: quote.close, changePct: quote.change_pct, label: '收盤', quoteTime: null }
  }
  return { price: quote.live_price, changePct: quote.change_pct, label: '即時', quoteTime: quote.quote_time }
}

const fmtTime = (iso) => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString('zh-TW', { hour12: false, timeZone: 'Asia/Taipei' })
  } catch {
    return ''
  }
}

// Small reference-index card next to the toolbar (^TWII, 0050) -- same
// live/close split as SideCell (sidePrice), just standalone instead of a
// table cell. Browsing a past date shows that date's close-based 漲跌幅
// instead of the live one, same as everything else quote-driven on this
// page (both come from the same /index-quotes?date= call).
function IndexQuoteCard({ label, quote }) {
  const { price, changePct, label: quoteLabel, quoteTime } = sidePrice(quote)
  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ color: 'var(--muted)', fontSize: 12 }}>{label}</div>
      {price != null ? (
        <>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{fmtPrice(price)}</div>
          <div style={{ fontSize: 12 }}>
            <span className={changeCls(changePct)}>{fmtChangePct(changePct)}</span>
            <span style={{ color: 'var(--muted)', marginLeft: 6 }}>
              {quoteLabel}{quoteTime && ` ${fmtTime(quoteTime)}`}
            </span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>—</div>
      )}
    </div>
  )
}

function SideCell({ name, quote, isTracked }) {
  const { price, changePct, label, quoteTime } = sidePrice(quote)
  return (
    <td>
      <span style={isTracked ? { color: '#ffd60a' } : undefined}>{name}</span>
      {price != null && (
        <div style={{ fontSize: 12 }}>
          <div style={{ color: 'var(--muted)' }}>
            股價({label}) {fmtPrice(price)}
            {quoteTime && <span style={{ marginLeft: 4 }}>{fmtTime(quoteTime)}</span>}
          </div>
          <div className={changeCls(changePct)}>漲跌幅 {fmtChangePct(changePct)}</div>
        </div>
      )}
    </td>
  )
}

const POS_H = 26
const POS_Y = 10
const POS_H_TRACK = 8

// The "目前配置" bar -- separate from ThresholdBar's "訊號" bar above it,
// on purpose: that one shows what the price data says (diff, tier
// thresholds, live quote); this one shows the actual manually-adjustable
// position (auto-computed unless overridden). Lighting is cumulative, not
// a single zone -- position 2 lights both the level-1 AND level-2 bands
// (like a level meter), matching how "you're 2 levels in" already implies
// "and therefore also 1 level in", not an either/or.
function PositionBar({ s, position, hasOverride, onAdjust, onReset }) {
  const marks = s.tier_marks || [{ tier: s.trigger }]
  const t1 = marks[0]?.tier ?? 1
  const t2 = marks[marks.length - 1]?.tier ?? t1
  const lo = -t2
  const hi = t2
  const span = hi - lo || 1
  const toX = (v) => ((Math.max(lo, Math.min(hi, v)) - lo) / span) * BAR_W

  const outerBoundFor = (pos) => {
    if (pos === 0) return 0
    const edge = Math.abs(pos) >= 2 ? t2 * 2 : t1 // level 1 -> T1; level 2 -> past T2 (toX clamps to the bar edge)
    return Math.sign(pos) * edge
  }
  const zeroX = toX(0)
  const fillX = toX(outerBoundFor(position))
  const color = position > 0 ? '#30a46c' : position < 0 ? '#e5484d' : '#f5a623'

  return (
    <div style={{ marginTop: 4 }}>
      <div className="row" style={{ gap: 4, alignItems: 'center', flexWrap: 'nowrap' }}>
        <button title={`往${s.nameA}那邊調一格`} onClick={() => onAdjust(-1)} disabled={position <= -2} style={{ padding: '0 6px' }}>◁</button>
        <svg width={BAR_W} height={POS_H} viewBox={`0 0 ${BAR_W} ${POS_H}`} style={{ overflow: 'visible' }}>
          <rect x={0} y={POS_Y} width={BAR_W} height={POS_H_TRACK} rx={3} fill="#3a3f4a" />
          {position === 0 ? (
            <rect x={zeroX - 2} y={POS_Y} width={4} height={POS_H_TRACK} fill={color} />
          ) : (
            <rect
              x={Math.min(zeroX, fillX)} y={POS_Y}
              width={Math.max(2, Math.abs(fillX - zeroX))} height={POS_H_TRACK}
              fill={color}
            />
          )}
          {[-t2, -t1, 0, t1, t2].map((v, i) => (
            <line key={i} x1={toX(v)} x2={toX(v)} y1={POS_Y - 4} y2={POS_Y + POS_H_TRACK + 4} stroke="#8a8f98" strokeWidth={1} />
          ))}
        </svg>
        <button title={`往${s.nameB}那邊調一格`} onClick={() => onAdjust(1)} disabled={position >= 2} style={{ padding: '0 6px' }}>▷</button>
        <button onClick={onReset} disabled={!hasOverride} style={{ padding: '0 6px', fontSize: 11 }}>恢復自動</button>
      </div>
    </div>
  )
}

// Same row content as PairStrategyShared's SignalRow, but with 訊號區間
// moved between A/B (instead of after both) and each side's name cell
// carrying its current price -- a page-specific layout, so this doesn't
// touch the shared component the other two pair-strategy tabs still use.
function LiteSignalRow({ s, trackedA, trackedB, live, quoteA, quoteB, override, onAdjustPosition, onResetOverride }) {
  if (s.error) {
    return (
      <tr>
        <td colSpan={5}>{s.label}：{s.error}</td>
      </tr>
    )
  }

  const entriesForDisplay = s.outcome_known ? s.entries_since_reset_after : s.entries_since_reset
  const browsingHistory = s.outcome_known // a specific past date is selected, not "predict next day"

  // Manual override only makes sense for "what's my position right now" --
  // editing a past date's outcome isn't meaningful, so history browsing
  // always shows the plain computed result, no light/arrows.
  const computedPosition = entriesForDisplay === 0 ? 0 : entriesForDisplay * (s.basis_diff >= 0 ? 1 : -1)
  const effPosition = !browsingHistory && override ? override.level * override.side : computedPosition

  return (
    <tr>
      <td><InfoIcon s={s} /></td>
      <SideCell name={s.nameA} quote={quoteA} isTracked={trackedA} />
      <td>
        <div className="row" style={{ gap: 4, alignItems: 'center', flexWrap: 'nowrap' }}>
          {!browsingHistory && (
            <button aria-hidden="true" tabIndex={-1} style={{ padding: '0 6px', visibility: 'hidden' }}>◁</button>
          )}
          <ThresholdBar
            s={s}
            liveDiff={!browsingHistory ? live?.live_diff : undefined}
            hideCaption={!browsingHistory}
          />
          {!browsingHistory && (
            <button aria-hidden="true" tabIndex={-1} style={{ padding: '0 6px', visibility: 'hidden' }}>▷</button>
          )}
        </div>
        {!browsingHistory && (
          <>
            <PositionBar
              s={s}
              position={effPosition}
              hasOverride={!!override}
              onAdjust={onAdjustPosition}
              onReset={onResetOverride}
            />
            <ThresholdBarCaption s={s} liveDiff={live?.live_diff} />
          </>
        )}
      </td>
      <SideCell name={s.nameB} quote={quoteB} isTracked={trackedB} />
      <td>
        {s.outcome_known ? (
          <>
            實際diff：{(s.actual_diff * 100).toFixed(2)}%
            <div style={{ color: 'var(--muted)', fontSize: 12 }}>
              {s.entered_today
                ? `✅ ${levelChangeLabel(s.entries_since_reset, s.entries_since_reset_after)}`
                : s.reset_today
                  ? '✅ 回到50/50'
                  : '未切換'}
            </div>
          </>
        ) : (
          <span style={{ color: 'var(--muted)' }}>尚未收盤，無結果</span>
        )}
      </td>
    </tr>
  )
}
