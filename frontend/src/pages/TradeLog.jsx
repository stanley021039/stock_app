import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

const money = (x) => (x == null ? '—' : Math.round(x).toLocaleString())
const pct = (x) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(1)}%`)
const colorPct = (x) => (x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat')
const todayStr = () => new Date().toISOString().slice(0, 10)

export default function TradeLog() {
  const [logs, setLogs] = useState(null)
  const [pairOptions, setPairOptions] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)

  const [name, setName] = useState('')
  const [pairChoice, setPairChoice] = useState('') // "source::key" or "" for custom
  const [customA, setCustomA] = useState({ symbol: '', name: '' })
  const [customB, setCustomB] = useState({ symbol: '', name: '' })
  const [initialCapital, setInitialCapital] = useState(1000000)
  const [startDate, setStartDate] = useState(todayStr())
  const [notes, setNotes] = useState('')
  const [creating, setCreating] = useState(false)

  function refresh() {
    api.listTradeLogs().then(setLogs).catch((e) => setError(e.message))
  }

  useEffect(() => {
    refresh()
    api.getTradeLogPairOptions().then((r) => setPairOptions(r.options)).catch((e) => setError(e.message))
  }, [])

  const selectedOption = useMemo(
    () => pairOptions.find((o) => `${o.source}::${o.key}` === pairChoice),
    [pairOptions, pairChoice],
  )

  function resetForm() {
    setName('')
    setPairChoice('')
    setCustomA({ symbol: '', name: '' })
    setCustomB({ symbol: '', name: '' })
    setInitialCapital(1000000)
    setStartDate(todayStr())
    setNotes('')
  }

  async function handleCreate() {
    setError(null)
    const symA = selectedOption ? selectedOption.symA : customA.symbol.trim()
    const symB = selectedOption ? selectedOption.symB : customB.symbol.trim()
    const nameA = selectedOption ? selectedOption.nameA : (customA.name.trim() || customA.symbol.trim())
    const nameB = selectedOption ? selectedOption.nameB : (customB.name.trim() || customB.symbol.trim())
    if (!name.trim() || !symA || !symB) {
      setError('請填寫名稱與兩檔標的')
      return
    }
    setCreating(true)
    try {
      await api.createTradeLog({
        name: name.trim(),
        pair_source: selectedOption ? selectedOption.source : null,
        pair_key: selectedOption ? selectedOption.key : null,
        symbol_a: symA,
        symbol_b: symB,
        name_a: nameA,
        name_b: nameB,
        initial_capital: Number(initialCapital) || 0,
        start_date: startDate,
        notes: notes.trim() || null,
      })
      resetForm()
      setShowForm(false)
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id, logName) {
    if (!window.confirm(`確定要刪除「${logName}」這組交易記錄嗎？（連同底下所有交易紀錄一併刪除，無法復原）`)) return
    try {
      await api.deleteTradeLog(id)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="section-title">
        <h2>真實交易記錄 Trade Log</h2>
        <button className="active" onClick={() => setShowForm((v) => !v)}>
          {showForm ? '取消' : '+ 新增一組'}
        </button>
      </div>

      {error && <div className="toast err" style={{ marginBottom: 12 }}>{error}</div>}

      {showForm && (
        <div className="editor">
          <div className="row" style={{ marginBottom: 10 }}>
            <label style={{ color: 'var(--muted)', fontSize: 13 }}>名稱</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：記憶體雙雄實盤" style={{ minWidth: 200 }} />
          </div>

          <div className="row" style={{ marginBottom: 10 }}>
            <label style={{ color: 'var(--muted)', fontSize: 13 }}>股對</label>
            <select value={pairChoice} onChange={(e) => setPairChoice(e.target.value)} style={{ minWidth: 220 }}>
              <option value="">（自訂標的）</option>
              {pairOptions.map((o) => (
                <option key={`${o.source}::${o.key}`} value={`${o.source}::${o.key}`}>
                  [{o.source_label}] {o.label}（{o.nameA}/{o.nameB}）
                </option>
              ))}
            </select>
          </div>

          {!selectedOption && (
            <div className="row" style={{ marginBottom: 10 }}>
              <input placeholder="A標的代號 (如 2330.TW)" value={customA.symbol}
                onChange={(e) => setCustomA((v) => ({ ...v, symbol: e.target.value }))} style={{ width: 150 }} />
              <input placeholder="A標的名稱" value={customA.name}
                onChange={(e) => setCustomA((v) => ({ ...v, name: e.target.value }))} style={{ width: 110 }} />
              <input placeholder="B標的代號" value={customB.symbol}
                onChange={(e) => setCustomB((v) => ({ ...v, symbol: e.target.value }))} style={{ width: 150 }} />
              <input placeholder="B標的名稱" value={customB.name}
                onChange={(e) => setCustomB((v) => ({ ...v, name: e.target.value }))} style={{ width: 110 }} />
            </div>
          )}

          <div className="row" style={{ marginBottom: 10 }}>
            <label style={{ color: 'var(--muted)', fontSize: 13 }}>初始投入資金</label>
            <input type="number" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} style={{ width: 130 }} />
            <label style={{ color: 'var(--muted)', fontSize: 13 }}>起始日（長抱比較基準）</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>

          <div className="row" style={{ marginBottom: 10 }}>
            <input placeholder="備註（選填）" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: '100%' }} />
          </div>

          <button className="active" onClick={handleCreate} disabled={creating}>
            {creating ? '建立中…' : '建立'}
          </button>
        </div>
      )}

      {logs && logs.length === 0 && !showForm && (
        <div style={{ color: 'var(--muted)' }}>還沒有任何交易記錄，點右上角「+ 新增一組」開始。</div>
      )}

      <div className="cards">
        {logs?.map((log) => {
          const s = log.summary
          return (
            <div key={log.id} className="card" style={{ cursor: 'default' }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Link to={`/trade-log/${log.id}`} style={{ flex: 1 }}>
                  <div className="name">{log.name}</div>
                  <div className="sym">{log.name_a}/{log.name_b}</div>
                </Link>
                <button onClick={() => handleDelete(log.id, log.name)} title="刪除" style={{ padding: '2px 8px' }}>✕</button>
              </div>
              <Link to={`/trade-log/${log.id}`}>
                <div className="price" style={{ marginTop: 8 }}>{money(s.market_value)}</div>
                <div className="chg">
                  <span className={colorPct(s.pnl_vs_initial_pct)}>對初始 {pct(s.pnl_vs_initial_pct)}</span>
                  {' ｜ '}
                  <span className={colorPct(s.pnl_vs_benchmark_pct)}>對長抱 {pct(s.pnl_vs_benchmark_pct)}</span>
                </div>
                <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 6 }}>
                  初始 {money(log.initial_capital)} ｜ {s.n_trades} 筆交易
                </div>
              </Link>
            </div>
          )
        })}
      </div>
    </div>
  )
}
