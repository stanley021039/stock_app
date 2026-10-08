import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

const REFRESH_MS = 30000

const fmtMoney = (x) => (x == null ? '—' : Math.round(x).toLocaleString())
const fmtPrice = (x) => (x == null ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: 2 }))
const fmtPct = (x) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}%`)
const cls = (x) => (x == null || x === 0 ? 'flat' : x > 0 ? 'up' : 'down')

// Read-only view of the Sinopac account's inventory (backend/holdings.py).
// Display only -- not wired into the pair strategy's position state, since
// part of the real portfolio lives at other brokers/accounts.
export default function Holdings() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState(null)

  async function load() {
    try {
      setData(await api.getHoldings())
      setUpdatedAt(new Date())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => clearInterval(t)
  }, [])

  const totals = data?.totals

  return (
    <div>
      <div className="section-title">
        <h2>庫存（永豐帳戶）</h2>
        <button onClick={load} disabled={loading}>⟳ 重新整理</button>
      </div>

      <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 12, lineHeight: 1.8 }}>
        <div>僅顯示永豐帳戶的庫存（零股以「股」計），每 {REFRESH_MS / 1000} 秒自動更新。</div>
        <div>目前不與配對策略的「目前配置」連動——實際持股還有一部分在其他帳戶。</div>
        <div>損益為永豐回報的數字（已扣預估手續費與證交稅），所以不會剛好等於「市值 − 成本」。</div>
      </div>

      {error && <div className="toast err" style={{ marginBottom: 12 }}>{error}</div>}
      {loading && !data && <div className="spinner">載入中…</div>}

      {totals && (
        <div className="editor" style={{ display: 'flex', gap: 40, flexWrap: 'wrap', marginBottom: 16 }}>
          <Stat label="總成本" value={fmtMoney(totals.cost)} />
          <Stat label="總市值" value={fmtMoney(totals.market_value)} />
          <Stat
            label="總損益"
            value={`${totals.pnl >= 0 ? '+' : ''}${fmtMoney(totals.pnl)}`}
            sub={fmtPct(totals.pnl_pct)}
            valueCls={cls(totals.pnl)}
          />
        </div>
      )}

      {data && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>股票</th>
                <th style={{ textAlign: 'right' }}>股數</th>
                <th style={{ textAlign: 'right' }}>成本均價</th>
                <th style={{ textAlign: 'right' }}>現價</th>
                <th style={{ textAlign: 'right' }}>今日漲跌</th>
                <th style={{ textAlign: 'right' }}>成本</th>
                <th style={{ textAlign: 'right' }}>市值</th>
                <th style={{ textAlign: 'right' }}>損益</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((p) => (
                <tr key={p.code}>
                  <td>
                    {p.symbol ? (
                      <Link to={`/stock/${encodeURIComponent(p.symbol)}`}>{p.name}</Link>
                    ) : (
                      p.name
                    )}
                    <span className="sym" style={{ marginLeft: 6 }}>{p.code}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>{p.quantity.toLocaleString()}</td>
                  <td style={{ textAlign: 'right' }}>{fmtPrice(p.avg_cost)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtPrice(p.last_price)}</td>
                  <td style={{ textAlign: 'right' }} className={cls(p.day_change_pct)}>{fmtPct(p.day_change_pct)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtMoney(p.cost)}</td>
                  <td style={{ textAlign: 'right' }}>{fmtMoney(p.market_value)}</td>
                  <td style={{ textAlign: 'right' }} className={cls(p.pnl)}>
                    {p.pnl == null ? '—' : `${p.pnl >= 0 ? '+' : ''}${fmtMoney(p.pnl)}`}
                    <div style={{ fontSize: 12 }}>{fmtPct(p.pnl_pct)}</div>
                  </td>
                </tr>
              ))}
              {data.positions.length === 0 && (
                <tr><td colSpan={8} style={{ color: 'var(--muted)' }}>目前沒有庫存</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {updatedAt && (
        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
          最後更新：{updatedAt.toLocaleTimeString('zh-TW', { hour12: false })}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, sub, valueCls }) {
  return (
    <div>
      <div style={{ color: 'var(--muted)', fontSize: 12 }}>{label}</div>
      <div className={valueCls} style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
      {sub && <div className={valueCls} style={{ fontSize: 12 }}>{sub}</div>}
    </div>
  )
}
