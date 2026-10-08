import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import EquityChart from '../components/EquityChart.jsx'

const RANGES = [
  ['1y', '1年'],
  ['3y', '3年'],
  ['5y', '5年'],
  ['10y', '10年'],
  ['max', '全部'],
]

const pct = (x) => (x == null ? '—' : `${(x * 100).toFixed(2)}%`)
const money = (x) => (x == null ? '—' : Math.round(x).toLocaleString())
const colorPct = (x) => (x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat')

export default function Backtest() {
  const [strategies, setStrategies] = useState([])
  const [strategy, setStrategy] = useState('sma_cross')
  const [params, setParams] = useState({})
  const [symbols, setSymbols] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [benchmark, setBenchmark] = useState('^TWII')
  const [range, setRange] = useState('3y')
  const [capital, setCapital] = useState(100000)
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    ;(async () => {
      const [strats, syms] = await Promise.all([api.getStrategies(), api.listSymbols()])
      setStrategies(strats)
      setSymbols(syms)
      const def = ['2330.TW', '2317.TW', 'AAPL', 'NVDA', 'MSFT'].filter((s) =>
        syms.some((x) => x.symbol === s),
      )
      setSelected(new Set(def))
    })()
  }, [])

  const currentStrat = strategies.find((s) => s.key === strategy)

  // Reset params to the strategy's defaults whenever the strategy changes.
  useEffect(() => {
    if (!currentStrat) return
    const init = {}
    currentStrat.params.forEach((p) => (init[p.name] = p.default))
    setParams(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategy, strategies.length])

  const indices = symbols.filter((s) => s.type === 'index')
  const pickable = symbols.filter((s) => s.type !== 'index')
  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase()
    return pickable.filter((s) => !n || `${s.symbol} ${s.name}`.toLowerCase().includes(n))
  }, [pickable, q])

  const toggle = (sym) =>
    setSelected((prev) => {
      const x = new Set(prev)
      x.has(sym) ? x.delete(sym) : x.add(sym)
      return x
    })

  async function run() {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.runBacktest({
        symbols: [...selected],
        strategy,
        params,
        range,
        benchmark: benchmark || null,
        initial_capital: Number(capital) || 100000,
      })
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const series = result
    ? [
        { name: '投資組合', color: '#2f81f7', data: result.portfolio.curve },
        ...(result.benchmark
          ? [{ name: `大盤 ${result.benchmark.symbol}`, color: '#e3b341', data: result.benchmark.curve }]
          : []),
      ]
    : []

  const pm = result?.portfolio?.metrics
  const bm = result?.benchmark?.metrics

  return (
    <div>
      <div className="section-title">
        <h2>回測 Backtest</h2>
      </div>

      <div className="editor">
        <div className="row" style={{ marginBottom: 12 }}>
          <label style={{ color: 'var(--muted)', fontSize: 13 }}>策略</label>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)} style={{ minWidth: 200 }}>
            {strategies.map((s) => (
              <option key={s.key} value={s.key}>{s.name}</option>
            ))}
          </select>

          {currentStrat?.params.map((p) => (
            <span key={p.name} className="row" style={{ gap: 4 }}>
              <label style={{ color: 'var(--muted)', fontSize: 13 }}>{p.label}</label>
              <input
                type="number"
                value={params[p.name] ?? p.default}
                onChange={(e) => setParams((prev) => ({ ...prev, [p.name]: Number(e.target.value) }))}
                style={{ width: 70 }}
              />
            </span>
          ))}
        </div>

        <div className="row" style={{ marginBottom: 12 }}>
          <label style={{ color: 'var(--muted)', fontSize: 13 }}>期間</label>
          {RANGES.map(([val, label]) => (
            <button key={val} className={range === val ? 'active' : ''} onClick={() => setRange(val)}>{label}</button>
          ))}
          <span style={{ width: 12 }} />
          <label style={{ color: 'var(--muted)', fontSize: 13 }}>大盤基準</label>
          <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
            <option value="">（不比較）</option>
            {indices.map((s) => (
              <option key={s.symbol} value={s.symbol}>{s.name}</option>
            ))}
          </select>
          <span style={{ width: 12 }} />
          <label style={{ color: 'var(--muted)', fontSize: 13 }}>本金</label>
          <input type="number" value={capital} onChange={(e) => setCapital(e.target.value)} style={{ width: 110 }} />
        </div>

        <div style={{ color: 'var(--muted)', fontSize: 13, margin: '4px 0 6px' }}>
          參與股票（等權重，已選 {selected.size} 檔）
        </div>
        <input
          placeholder="搜尋加入…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: '100%', marginBottom: 8 }}
        />
        <div
          style={{
            maxHeight: 180,
            overflowY: 'auto',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: '2px 12px',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: 8,
          }}
        >
          {filtered.map((s) => (
            <label className="checkrow" key={s.symbol} style={{ padding: '3px 0' }}>
              <input type="checkbox" checked={selected.has(s.symbol)} onChange={() => toggle(s.symbol)} style={{ width: 'auto' }} />
              <span style={{ fontSize: 13 }}>{s.symbol}</span>
              <span className="sym" style={{ fontSize: 12 }}>{s.name}</span>
            </label>
          ))}
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <button className="active" onClick={run} disabled={running || selected.size === 0}>
            {running ? '回測中…' : '▶ 執行回測'}
          </button>
          {error && <span className="toast err">{error}</span>}
        </div>
      </div>

      {result && (
        <>
          <div className="row" style={{ gap: 18, marginBottom: 8 }}>
            <span style={{ color: '#2f81f7' }}>● 投資組合</span>
            {result.benchmark && <span style={{ color: '#e3b341' }}>● 大盤 {result.benchmark.symbol}</span>}
          </div>

          <table style={{ marginBottom: 8 }}>
            <thead>
              <tr>
                <th>指標</th>
                <th style={{ textAlign: 'right' }}>投資組合</th>
                <th style={{ textAlign: 'right' }}>大盤</th>
              </tr>
            </thead>
            <tbody>
              <MetricRow label="總報酬" p={pct(pm?.total_return)} b={pct(bm?.total_return)} pc={colorPct(pm?.total_return)} bc={colorPct(bm?.total_return)} />
              <MetricRow label="年化報酬 (CAGR)" p={pct(pm?.cagr)} b={pct(bm?.cagr)} pc={colorPct(pm?.cagr)} bc={colorPct(bm?.cagr)} />
              <MetricRow label="年化波動" p={pct(pm?.ann_vol)} b={pct(bm?.ann_vol)} />
              <MetricRow label="Sharpe" p={pm?.sharpe?.toFixed(2) ?? '—'} b={bm?.sharpe?.toFixed(2) ?? '—'} />
              <MetricRow label="最大回撤" p={pct(pm?.max_drawdown)} b={pct(bm?.max_drawdown)} pc="down" bc="down" />
              <MetricRow label="期末資產" p={money(pm?.final_value)} b={money(bm?.final_value)} />
            </tbody>
          </table>

          <div className="chart-wrap">
            <EquityChart series={series} />
          </div>

          <div className="meta">
            參與 {result.symbols_used.length} 檔：{result.symbols_used.join(', ')}
            {result.symbols_missing.length > 0 && ` ｜ 無資料略過：${result.symbols_missing.join(', ')}`}
          </div>
        </>
      )}
    </div>
  )
}

function MetricRow({ label, p, b, pc, bc }) {
  return (
    <tr style={{ cursor: 'default' }}>
      <td>{label}</td>
      <td style={{ textAlign: 'right' }} className={pc || ''}>{p}</td>
      <td style={{ textAlign: 'right' }} className={bc || ''}>{b}</td>
    </tr>
  )
}
