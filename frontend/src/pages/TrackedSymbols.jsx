import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import Quote from '../components/Quote.jsx'
import { useDragReorder } from '../lib/useDragReorder.js'

// Manage the global live-quote watchlist (backend/quote_tracker.py). Any
// symbol added here gets its TODAY price kept continuously fresh off
// Sinopac while the market's open -- every other page in the app (Home,
// stock detail, 真實交易記錄, ...) just reads db.latest_quote/get_prices,
// so tracking a symbol here is the one lever that makes it live everywhere.
export default function TrackedSymbols() {
  const [tracked, setTracked] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [busySymbol, setBusySymbol] = useState(null)

  function refresh() {
    return api.getTrackedSymbols().then(setTracked).catch((e) => setError(e.message))
  }

  useEffect(() => {
    setLoading(true)
    refresh().finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const needle = q.trim()
    if (!needle) {
      setResults([])
      return
    }
    setSearching(true)
    const t = setTimeout(() => {
      api.listSymbols({ q: needle })
        .then(setResults)
        .catch((e) => setError(e.message))
        .finally(() => setSearching(false))
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  const trackedSet = useMemo(() => new Set(tracked.map((s) => s.symbol)), [tracked])

  const reorder = useDragReorder(tracked, (s) => s.symbol, async (next) => {
    setTracked(next) // optimistic -- the row lands immediately
    try {
      setTracked(await api.setTrackedOrder(next.map((s) => s.symbol)))
    } catch (e) {
      setError(e.message)
      refresh()
    }
  })

  async function handleAdd(symbol) {
    setBusySymbol(symbol)
    setError(null)
    try {
      setTracked(await api.addTrackedSymbol(symbol))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusySymbol(null)
    }
  }

  async function handleTogglePipHidden(s) {
    setBusySymbol(s.symbol)
    setError(null)
    try {
      setTracked(await api.setTrackedPipHidden(s.symbol, !s.pip_hidden))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusySymbol(null)
    }
  }

  async function handleRemove(symbol) {
    setBusySymbol(symbol)
    setError(null)
    try {
      setTracked(await api.removeTrackedSymbol(symbol))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusySymbol(null)
    }
  }

  return (
    <div>
      <div className="section-title">
        <h2>報價追蹤 Tracked Symbols</h2>
      </div>

      <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 16 }}>
        這裡加入的股票，開盤期間(平日09:00-13:30)會用永豐即時報價每15秒自動更新它當天的價格，
        全站(首頁、個股頁、真實交易記錄…)都會直接顯示這個即時價；沒加入的股票則維持顯示最近一次收盤價。
      </div>

      {error && <div className="toast err" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="editor" style={{ marginBottom: 16 }}>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 8 }}>搜尋股票加入追蹤</div>
        <input
          placeholder="輸入代號或名稱… (2330 / 台積電 / 國巨)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: '100%' }}
        />
        {q.trim() && (
          <div style={{ marginTop: 10, maxHeight: 220, overflowY: 'auto' }}>
            {searching && <div className="spinner">搜尋中…</div>}
            {!searching && results.length === 0 && (
              <div style={{ color: 'var(--muted)', fontSize: 13 }}>沒有符合的股票（需先在首頁「＋新增股票」加入股票清單）</div>
            )}
            {results.map((s) => {
              const already = trackedSet.has(s.symbol)
              return (
                <div key={s.symbol} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>
                    <span style={{ fontWeight: 600 }}>{s.symbol}</span>{' '}
                    <span className="sym">{s.name}</span>
                  </span>
                  <button
                    className={already ? '' : 'active'}
                    onClick={() => (already ? handleRemove(s.symbol) : handleAdd(s.symbol))}
                    disabled={busySymbol === s.symbol}
                  >
                    {already ? '已追蹤，移除' : '+ 加入追蹤'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="section-title">
        <h2>追蹤中（{tracked.length}）</h2>
      </div>
      {loading ? (
        <div className="spinner">載入中…</div>
      ) : tracked.length === 0 ? (
        <div style={{ color: 'var(--muted)' }}>還沒有追蹤任何股票，上面搜尋加入。</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th></th>
              <th>代號</th>
              <th>名稱</th>
              <th style={{ textAlign: 'right' }}>最新價</th>
              <th style={{ textAlign: 'right' }}>漲跌</th>
              <th style={{ textAlign: 'center' }} title="只影響子母視窗，網頁仍會顯示">子母視窗</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tracked.map((s) => (
              <tr key={s.symbol} {...reorder.rowProps(s)} style={{ cursor: 'default', ...reorder.rowProps(s).style }}>
                <td {...reorder.handleProps(s)}>⋮⋮</td>
                <td style={{ fontWeight: 600 }}>{s.symbol}</td>
                <td style={{ color: '#ffd60a' }}>{s.name}</td>
                <td style={{ textAlign: 'right' }}>
                  {s.quote?.price != null ? s.quote.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
                </td>
                <td style={{ textAlign: 'right' }}><Quote quote={s.quote} inline /></td>
                <td style={{ textAlign: 'center' }}>
                  <button
                    onClick={() => handleTogglePipHidden(s)}
                    disabled={busySymbol === s.symbol}
                    title={s.pip_hidden ? '目前不在子母視窗顯示，按一下恢復' : '按一下在子母視窗隱藏（網頁仍顯示）'}
                    aria-label={s.pip_hidden ? '在子母視窗顯示' : '在子母視窗隱藏'}
                    style={{ padding: '3px 8px', lineHeight: 0, ...(s.pip_hidden ? { color: 'var(--muted)', opacity: 0.6 } : {}) }}
                  >
                    {s.pip_hidden ? <EyeOffIcon /> : <EyeIcon />}
                  </button>
                </td>
                <td>
                  <button onClick={() => handleRemove(s.symbol)} disabled={busySymbol === s.symbol} style={{ padding: '2px 8px' }}>
                    移除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

const iconProps = {
  width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
}

function EyeIcon() {
  return (
    <svg {...iconProps}>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg {...iconProps}>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}
