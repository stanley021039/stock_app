import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import Quote from '../components/Quote.jsx'

export default function Home() {
  const navigate = useNavigate()
  const [indices, setIndices] = useState([])
  const [symbols, setSymbols] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [updatingAll, setUpdatingAll] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [toast, setToast] = useState(null)

  // selector filters
  const [q, setQ] = useState('')
  const [market, setMarket] = useState('')
  const [type, setType] = useState('')

  async function load() {
    setLoading(true)
    const [idx, syms] = await Promise.all([
      api.getHomeIndices(),
      api.listSymbols({ withQuote: true }),
    ])
    setIndices(idx)
    setSymbols(syms)
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return symbols.filter((s) => {
      if (market && s.market !== market) return false
      if (type && s.type !== type) return false
      if (needle && !(`${s.symbol} ${s.name}`.toLowerCase().includes(needle))) return false
      return true
    })
  }, [symbols, q, market, type])

  const go = (symbol) => navigate(`/stock/${encodeURIComponent(symbol)}`)

  async function onUpdateAll() {
    setUpdatingAll(true)
    setToast(null)
    try {
      const r = await api.updateAll()
      const failTxt = r.failed.length ? `，失敗 ${r.failed.length} 檔` : ''
      setToast({ ok: r.failed.length === 0, msg: `全部更新完成：${r.updated}/${r.symbols} 檔，新增 ${r.rows_written} 筆${failTxt}` })
      await load()
    } catch (e) {
      setToast({ ok: false, msg: `更新失敗：${e.message}` })
    } finally {
      setUpdatingAll(false)
    }
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="row" style={{ marginBottom: 16 }}>
        <button onClick={onUpdateAll} disabled={updatingAll} title="向 Yahoo 增量更新所有追蹤標的">
          {updatingAll ? '全部更新中…（可能需 1 分鐘）' : '⟳ 一鍵全部更新'}
        </button>
        <button className={addOpen ? 'active' : ''} onClick={() => setAddOpen((v) => !v)}>＋ 新增股票</button>
        {toast && <span className={`toast ${toast.ok ? 'ok' : 'err'}`}>{toast.msg}</span>}
      </div>

      {addOpen && (
        <AddSymbol
          onAdded={async (msg) => {
            setToast({ ok: true, msg })
            await load()
            setAddOpen(false)
          }}
          onError={(msg) => setToast({ ok: false, msg })}
        />
      )}

      {/* Indices */}
      <div className="section-title">
        <h2>指數 Indices</h2>
        <button onClick={() => setEditing((v) => !v)}>{editing ? '完成' : '編輯'}</button>
      </div>

      {editing && (
        <IndexEditor
          allIndices={symbols.filter((s) => s.type === 'index')}
          current={indices.map((i) => i.symbol)}
          onSave={async (next) => {
            await api.setHomeIndices(next)
            await load()
            setEditing(false)
          }}
        />
      )}

      {loading ? (
        <div className="spinner">載入中…</div>
      ) : (
        <div className="cards">
          {indices.map((it) => (
            <div className="card" key={it.symbol} onClick={() => go(it.symbol)}>
              <div className="name">{it.name}</div>
              <div className="price">
                {it.quote?.price != null ? it.quote.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
              </div>
              <Quote quote={it.quote} />
              <div className="sym">{it.symbol}</div>
            </div>
          ))}
          {indices.length === 0 && <div className="spinner">尚未設定指數，按「編輯」新增。</div>}
        </div>
      )}

      {/* Stock selector */}
      <div className="section-title" style={{ marginTop: 32 }}>
        <h2>選擇股票 Pick a stock</h2>
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>{filtered.length} 檔</span>
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input
          placeholder="搜尋代號或名稱… (2330 / TSMC / AAPL)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">全部市場</option>
          <option value="TW">台股</option>
          <option value="US">美股</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">全部類型</option>
          <option value="index">指數</option>
          <option value="stock">個股</option>
          <option value="etf">ETF</option>
        </select>
      </div>

      <table>
        <thead>
          <tr>
            <th>代號</th>
            <th>名稱</th>
            <th>市場</th>
            <th>類型</th>
            <th style={{ textAlign: 'right' }}>最新價</th>
            <th style={{ textAlign: 'right' }}>漲跌</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((s) => (
            <tr key={s.symbol} onClick={() => go(s.symbol)}>
              <td style={{ fontWeight: 600 }}>{s.symbol}</td>
              <td>
                <span style={s.is_tracked ? { color: '#ffd60a' } : undefined} title={s.is_tracked ? '報價追蹤中，價格為即時' : undefined}>
                  {s.name}
                </span>
              </td>
              <td><span className="badge">{s.market}</span></td>
              <td><span className="badge">{s.type}</span></td>
              <td style={{ textAlign: 'right' }}>
                {s.quote?.price != null ? s.quote.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
              </td>
              <td style={{ textAlign: 'right' }}>
                <Quote quote={s.quote} inline />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function IndexEditor({ allIndices, current, onSave }) {
  const [selected, setSelected] = useState(new Set(current))
  const toggle = (sym) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(sym) ? next.delete(sym) : next.add(sym)
      return next
    })
  }
  return (
    <div className="editor">
      <div style={{ marginBottom: 8, color: 'var(--muted)', fontSize: 13 }}>
        勾選要顯示在首頁的指數：
      </div>
      {allIndices.map((s) => (
        <label className="checkrow" key={s.symbol}>
          <input
            type="checkbox"
            checked={selected.has(s.symbol)}
            onChange={() => toggle(s.symbol)}
            style={{ width: 'auto' }}
          />
          <span>{s.name}</span>
          <span className="sym">({s.symbol})</span>
        </label>
      ))}
      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="active"
          onClick={() => onSave(allIndices.filter((s) => selected.has(s.symbol)).map((s) => s.symbol))}
        >
          儲存
        </button>
      </div>
    </div>
  )
}

function AddSymbol({ onAdded, onError }) {
  const [symbol, setSymbol] = useState('')
  const [name, setName] = useState('')
  const [market, setMarket] = useState('')
  const [type, setType] = useState('stock')
  const [busy, setBusy] = useState(false)

  async function submit() {
    const sym = symbol.trim()
    if (!sym) return
    setBusy(true)
    try {
      const body = { symbol: sym, type }
      if (name.trim()) body.name = name.trim()
      if (market) body.market = market
      const r = await api.addSymbol(body)
      onAdded(`已新增 ${r.symbol}：抓到 ${r.rows_written} 筆，最新 ${r.last_date}`)
      setSymbol('')
      setName('')
    } catch (e) {
      onError(`新增失敗：${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="editor">
      <div style={{ marginBottom: 8, color: 'var(--muted)', fontSize: 13 }}>
        輸入 Yahoo 代號（台股 <code>2330.TW</code>、上櫃 <code>5483.TWO</code>、美股 <code>AAPL</code>）。新增後會自動抓全部歷史。
      </div>
      <div className="row">
        <input placeholder="代號 *" value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ width: 140 }} />
        <input placeholder="名稱（可留空）" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1, minWidth: 160 }} />
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">市場(自動)</option>
          <option value="TW">台股</option>
          <option value="US">美股</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="stock">個股</option>
          <option value="etf">ETF</option>
          <option value="index">指數</option>
        </select>
        <button className="active" onClick={submit} disabled={busy}>
          {busy ? '抓取中…' : '新增並下載'}
        </button>
      </div>
    </div>
  )
}
