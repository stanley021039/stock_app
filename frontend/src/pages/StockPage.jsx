import { useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api.js'
import PriceChart from '../components/PriceChart.jsx'
import Quote from '../components/Quote.jsx'

const RANGES_DAILY = [
  ['1mo', '1月'],
  ['3mo', '3月'],
  ['6mo', '6月'],
  ['1y', '1年'],
  ['5y', '5年'],
  ['max', '全部'],
]
const RANGES_INTRADAY = [
  ['1d', '1日'],
  ['5d', '5日'],
  ['1mo', '1月'],
  ['max', '60日'],
]
const DEFAULT_RANGE = { '1d': '6mo', '5m': '5d' }

export default function StockPage() {
  const { symbol } = useParams()
  const [meta, setMeta] = useState(null)
  const [prices, setPrices] = useState([])
  const [tick, setTick] = useState('1d') // '1d' | '5m'
  const [range, setRange] = useState('6mo') // default: 6 months
  const [kind, setKind] = useState(null) // null = auto by type
  const [showMA, setShowMA] = useState(true)
  const [showKD, setShowKD] = useState(false)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [toast, setToast] = useState(null)

  const maList = useMemo(() => (showMA ? [5, 20, 60] : []), [showMA])
  const ranges = tick === '1d' ? RANGES_DAILY : RANGES_INTRADAY
  const intraday = tick !== '1d'
  // Unify daily ('date' string) and intraday ('time' epoch) into one `time` field.
  const bars = useMemo(() => prices.map((p) => ({ ...p, time: p.time ?? p.date })), [prices])

  async function loadMeta() {
    setMeta(await api.getSymbol(symbol))
  }

  async function loadPrices(r, iv) {
    setLoading(true)
    const res = await api.getPrices(symbol, r, iv)
    setPrices(res.prices)
    setLoading(false)
  }

  useEffect(() => {
    setMeta(null)
    setKind(null)
    loadMeta()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  useEffect(() => {
    loadPrices(range, tick)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, range, tick])

  function switchTick(iv) {
    if (iv === tick) return
    setTick(iv)
    setRange(DEFAULT_RANGE[iv])
  }

  async function onUpdate() {
    setUpdating(true)
    setToast(null)
    try {
      const r = await api.updateSymbol(symbol, tick)
      const tail = r.last_date ? `，最新 ${r.last_date}` : ''
      setToast({ ok: true, msg: `已更新${intraday ? ' 5分線' : ' 日線'}：新增 ${r.rows_written} 筆${tail}（共 ${r.total_bars} 筆）` })
      await loadMeta()
      await loadPrices(range, tick)
    } catch (e) {
      setToast({ ok: false, msg: `更新失敗：${e.message}` })
    } finally {
      setUpdating(false)
    }
  }

  const effectiveKind = kind ?? (meta?.type === 'index' ? 'area' : 'candle')

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <Link to="/">← 返回</Link>
      </div>

      <div className="stock-head">
        <span className="big">{symbol}</span>
        <span className="sub" style={meta?.is_tracked ? { color: '#ffd60a' } : undefined} title={meta?.is_tracked ? '報價追蹤中，價格為即時' : undefined}>
          {meta?.name ?? ''}
        </span>
        {meta?.quote?.price != null && (
          <>
            <span className="big" style={{ fontSize: 22 }}>
              {meta.quote.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
            <Quote quote={meta.quote} inline />
          </>
        )}
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        {ranges.map(([val, label]) => (
          <button key={val} className={range === val ? 'active' : ''} onClick={() => setRange(val)}>
            {label}
          </button>
        ))}
        <span style={{ width: 12 }} />
        <button className={tick === '1d' ? 'active' : ''} onClick={() => switchTick('1d')}>日線</button>
        <button className={tick === '5m' ? 'active' : ''} onClick={() => switchTick('5m')}>5分線</button>
        <span style={{ flex: 1 }} />
        <button className={effectiveKind === 'candle' ? 'active' : ''} onClick={() => setKind('candle')}>K線</button>
        <button className={effectiveKind === 'area' ? 'active' : ''} onClick={() => setKind('area')}>折線</button>
        <button onClick={onUpdate} disabled={updating} title="向 Yahoo 爬取最新資料">
          {updating ? '更新中…' : '⟳ 更新資料'}
        </button>
      </div>

      <div className="row" style={{ marginTop: 8 }}>
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>技術指標：</span>
        <button className={showMA ? 'active' : ''} onClick={() => setShowMA((v) => !v)}>MA 5/20/60</button>
        <button className={showKD ? 'active' : ''} onClick={() => setShowKD((v) => !v)}>KD (9,3,3)</button>
        {intraday && <span style={{ color: 'var(--muted)', fontSize: 12 }}>· 5分線僅提供約 60 天</span>}
      </div>

      {toast && (
        <div className="row" style={{ marginTop: 10 }}>
          <span className={`toast ${toast.ok ? 'ok' : 'err'}`}>{toast.msg}</span>
        </div>
      )}

      <div className="chart-wrap">
        {loading ? (
          <div className="spinner" style={{ padding: 40 }}>載入中…</div>
        ) : bars.length === 0 ? (
          <div className="spinner" style={{ padding: 40 }}>
            此區間無資料，試試按「更新資料」{intraday ? '抓取 5 分線' : ''}。
          </div>
        ) : (
          <PriceChart data={bars} kind={effectiveKind} maList={maList} showKD={showKD} intraday={intraday} />
        )}
      </div>

      {meta && (
        <div className="meta">
          市場 {meta.market} · 類型 {meta.type}
          {tick === '1d' && meta.bars != null && ` · 日線共 ${meta.bars} 筆`}
          {tick === '1d' && meta.last_date && ` · 最新 ${meta.last_date}`}
          {bars.length > 0 && ` · 本區間 ${bars.length} 筆`}
        </div>
      )}
    </div>
  )
}
