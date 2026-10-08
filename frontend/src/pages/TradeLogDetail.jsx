import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api.js'

const money = (x) => (x == null ? '—' : Math.round(x).toLocaleString())
const pct = (x) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(1)}%`)
const colorPct = (x) => (x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat')
// Buy/sell action color -- opposite sense from colorPct (spending cash = red,
// receiving cash = green), matching the entries table's 買進/賣出 coloring.
const actionCls = (x) => (x == null ? '' : x > 0 ? 'down' : x < 0 ? 'up' : '')
const todayStr = () => new Date().toISOString().slice(0, 10)
const shareStr = (x) => (x == null ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: 1 }))

export default function TradeLogDetail() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const [date, setDate] = useState(todayStr())
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState('buy')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState(0)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const [editingLog, setEditingLog] = useState(false)
  const [editCapital, setEditCapital] = useState('')
  const [editStartDate, setEditStartDate] = useState('')
  const [savingLog, setSavingLog] = useState(false)

  // Local drafts so the input stays responsive while typing digit-by-digit;
  // each keystroke persists to the DB (price_a/price_b or start_price_a/b
  // columns on trade_logs -- see db.py) so the custom price survives
  // navigating away and coming back, not just this page's own state.
  const [priceADraft, setPriceADraft] = useState('')
  const [priceBDraft, setPriceBDraft] = useState('')
  const [startPriceADraft, setStartPriceADraft] = useState('')
  const [startPriceBDraft, setStartPriceBDraft] = useState('')

  function refresh() {
    api.getTradeLog(id).then((r) => {
      setData(r)
      setSymbol((prev) => prev || r.log.symbol_a)
      setPriceADraft((prev) => prev || String(r.summary.price_a ?? ''))
      setPriceBDraft((prev) => prev || String(r.summary.price_b ?? ''))
      setStartPriceADraft((prev) => prev || String(r.summary.start_price_a ?? ''))
      setStartPriceBDraft((prev) => prev || String(r.summary.start_price_b ?? ''))
    }).catch((e) => setError(e.message))
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  async function commitPrice(nextA, nextB) {
    const a = Number(nextA), b = Number(nextB)
    if (!nextA || !nextB || Number.isNaN(a) || Number.isNaN(b)) return
    try {
      setData(await api.setTradeLogPrice(id, { price_a: a, price_b: b }))
    } catch (e) {
      setError(e.message)
    }
  }

  function handlePriceAChange(v) {
    setPriceADraft(v)
    commitPrice(v, priceBDraft)
  }

  function handlePriceBChange(v) {
    setPriceBDraft(v)
    commitPrice(priceADraft, v)
  }

  async function handleTrackLatest() {
    try {
      const r = await api.clearTradeLogPrice(id)
      setData(r)
      setPriceADraft(String(r.summary.price_a ?? ''))
      setPriceBDraft(String(r.summary.price_b ?? ''))
    } catch (e) {
      setError(e.message)
    }
  }

  async function commitStartPrice(nextA, nextB) {
    const a = Number(nextA), b = Number(nextB)
    if (!nextA || !nextB || Number.isNaN(a) || Number.isNaN(b)) return
    try {
      setData(await api.setTradeLogStartPrice(id, { start_price_a: a, start_price_b: b }))
    } catch (e) {
      setError(e.message)
    }
  }

  function handleStartPriceAChange(v) {
    setStartPriceADraft(v)
    commitStartPrice(v, startPriceBDraft)
  }

  function handleStartPriceBChange(v) {
    setStartPriceBDraft(v)
    commitStartPrice(startPriceADraft, v)
  }

  async function handleTrackStartDate() {
    try {
      const r = await api.clearTradeLogStartPrice(id)
      setData(r)
      setStartPriceADraft(String(r.summary.start_price_a ?? ''))
      setStartPriceBDraft(String(r.summary.start_price_b ?? ''))
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleAdd() {
    setError(null)
    if (!shares || !price) {
      setError('請填寫股數與價格')
      return
    }
    setSaving(true)
    try {
      await api.addTradeEntry(id, {
        date, symbol, side,
        shares: Number(shares), price: Number(price), fee: Number(fee) || 0,
        note: note.trim() || null,
      })
      setShares('')
      setPrice('')
      setFee(0)
      setNote('')
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  function startEditLog() {
    setEditCapital(log.initial_capital)
    setEditStartDate(log.start_date)
    setEditingLog(true)
  }

  async function handleSaveLog() {
    setError(null)
    setSavingLog(true)
    try {
      await api.updateTradeLog(id, {
        initial_capital: Number(editCapital) || 0,
        start_date: editStartDate,
      })
      setEditingLog(false)
      if (editStartDate !== log.start_date && d.start_price_is_custom) {
        // the persisted start-price override no longer matches the new
        // start_date -- clear it so it goes back to auto-tracking
        await handleTrackStartDate()
      } else {
        refresh()
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingLog(false)
    }
  }

  async function handleDeleteEntry(entryId) {
    if (!window.confirm('確定要刪除這筆交易嗎？')) return
    try {
      await api.deleteTradeEntry(id, entryId)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleToggleIncluded(entryId, included) {
    try {
      await api.setTradeEntryIncluded(id, entryId, included)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  if (!data) return <div style={{ color: 'var(--muted)' }}>{error || '載入中…'}</div>

  const { log, entries, summary: s, summary_excluding_off: sx } = data
  const anyExcluded = entries.some((e) => !e.included)
  const d = anyExcluded ? sx : s

  return (
    <div>
      <div className="section-title">
        <h2><Link to="/trade-log" style={{ color: 'var(--muted)' }}>真實交易記錄</Link> / {log.name}</h2>
      </div>

      {error && <div className="toast err" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="editor" style={{ marginBottom: 16, borderColor: anyExcluded ? 'var(--accent)' : 'var(--border)' }}>
        <div className="row" style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 10, flexWrap: 'wrap' }}>
          <span>{log.name_a}（{log.symbol_a}）/ {log.name_b}（{log.symbol_b}）</span>
          {editingLog ? (
            <>
              <span>｜ 初始資金</span>
              <input type="number" value={editCapital} onChange={(e) => setEditCapital(e.target.value)} style={{ width: 110 }} />
              <span>起始日</span>
              <input type="date" value={editStartDate} onChange={(e) => setEditStartDate(e.target.value)} />
              <button className="active" onClick={handleSaveLog} disabled={savingLog}>{savingLog ? '儲存中…' : '儲存'}</button>
              <button onClick={() => setEditingLog(false)} disabled={savingLog}>取消</button>
            </>
          ) : (
            <>
              <span>｜ 初始資金 {money(log.initial_capital)} ｜ 起始日 {log.start_date}</span>
              <button onClick={startEditLog} style={{ padding: '2px 8px' }}>編輯</button>
            </>
          )}
          {log.notes && <span>｜ {log.notes}</span>}
          {anyExcluded && <span>（已排除「計入」關閉的交易，剩下 {d.n_trades} 筆重新試算）</span>}
        </div>
        <PriceRow
          label={`起始股價（${log.start_date}）`}
          nameA={log.name_a} nameB={log.name_b}
          valueA={startPriceADraft} valueB={startPriceBDraft}
          onChangeA={handleStartPriceAChange} onChangeB={handleStartPriceBChange}
          isCustom={d.start_price_is_custom}
          onTrack={handleTrackStartDate} trackLabel="追蹤起始日收盤價"
        />
        <PriceRow
          label="統計參考股價"
          nameA={log.name_a} nameB={log.name_b}
          valueA={priceADraft} valueB={priceBDraft}
          onChangeA={handlePriceAChange} onChangeB={handlePriceBChange}
          isCustom={d.price_is_custom}
          isLive={d.price_a_is_live || d.price_b_is_live}
          onTrack={handleTrackLatest} trackLabel="追蹤最近收盤價"
        />
        <div className="row" style={{ gap: 24, flexWrap: 'wrap' }}>
          <Stat label="目前市值" value={money(d.market_value)} />
          <Stat label="現金" value={money(d.cash)} />
          <Stat label={`持股 ${log.name_a}`} value={`${d.holdings[log.symbol_a]?.toLocaleString() ?? 0} 股`} />
          <Stat label={`持股 ${log.name_b}`} value={`${d.holdings[log.symbol_b]?.toLocaleString() ?? 0} 股`} />
          <Stat label="累計手續費/稅" value={money(d.total_fees)} />
        </div>
        <div className="row" style={{ gap: 24, flexWrap: 'wrap', marginTop: 14 }}>
          <Stat label="對初始資金盈虧" value={`${money(d.pnl_vs_initial)}（${pct(d.pnl_vs_initial_pct)}）`} cls={colorPct(d.pnl_vs_initial_pct)} />
          <Stat
            label="對長抱（50/50買進持有）盈虧"
            value={d.benchmark_value == null ? '—' : `${money(d.pnl_vs_benchmark)}（${pct(d.pnl_vs_benchmark_pct)}）`}
            cls={colorPct(d.pnl_vs_benchmark_pct)}
          />
          <Stat label="長抱本身報酬" value={pct(d.benchmark_return_pct)} cls={colorPct(d.benchmark_return_pct)} />
        </div>
      </div>

      <RebalanceCalc log={log} d={d} />

      <div className="editor" style={{ marginBottom: 16 }}>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 8 }}>新增一筆交易</div>
        <div className="row">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            <option value={log.symbol_a}>{log.name_a}（{log.symbol_a}）</option>
            <option value={log.symbol_b}>{log.name_b}（{log.symbol_b}）</option>
          </select>
          <select value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="buy">買進</option>
            <option value="sell">賣出</option>
          </select>
          <input type="number" placeholder="股數" value={shares} onChange={(e) => setShares(e.target.value)} style={{ width: 100 }} />
          <input type="number" placeholder="價格" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 100 }} />
          <input type="number" placeholder="手續費/稅" value={fee} onChange={(e) => setFee(e.target.value)} style={{ width: 100 }} />
          <input placeholder="備註（選填）" value={note} onChange={(e) => setNote(e.target.value)} style={{ width: 160 }} />
          <button className="active" onClick={handleAdd} disabled={saving}>{saving ? '新增中…' : '新增'}</button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>計入</th>
              <th>日期</th>
              <th>標的</th>
              <th>方向</th>
              <th style={{ textAlign: 'right' }}>股數</th>
              <th style={{ textAlign: 'right' }}>價格</th>
              <th style={{ textAlign: 'right' }}>成交金額</th>
              <th style={{ textAlign: 'right' }}>手續費/稅</th>
              <th>備註</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr style={{ cursor: 'default' }}>
                <td colSpan={10} style={{ color: 'var(--muted)' }}>還沒有交易紀錄</td>
              </tr>
            )}
            {entries.map((e) => (
              <tr key={e.id} style={{ cursor: 'default', opacity: e.included ? 1 : 0.5 }}>
                <td>
                  <input
                    type="checkbox"
                    checked={!!e.included}
                    onChange={(ev) => handleToggleIncluded(e.id, ev.target.checked)}
                    title="關閉＝算「如果沒有這筆交易」的假設結果時排除它"
                  />
                </td>
                <td>{e.date}</td>
                <td>{e.symbol === log.symbol_a ? log.name_a : log.name_b}</td>
                <td className={e.side === 'buy' ? 'down' : 'up'}>{e.side === 'buy' ? '買進' : '賣出'}</td>
                <td style={{ textAlign: 'right' }}>{e.shares.toLocaleString()}</td>
                <td style={{ textAlign: 'right' }}>{e.price}</td>
                <td style={{ textAlign: 'right' }}>{money(e.shares * e.price)}</td>
                <td style={{ textAlign: 'right' }}>{money(e.fee)}</td>
                <td style={{ color: 'var(--muted)' }}>{e.note || ''}</td>
                <td><button onClick={() => handleDeleteEntry(e.id)} style={{ padding: '2px 8px' }}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const PRICE_ROW_COLS = '180px 44px 90px 44px 90px 46px auto'

function PriceRow({ label, nameA, nameB, valueA, valueB, onChangeA, onChangeB, isCustom, isLive, onTrack, trackLabel }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: PRICE_ROW_COLS, alignItems: 'center', gap: 8, marginBottom: 10 }}>
      <label style={{ color: 'var(--muted)', fontSize: 13 }}>{label}</label>
      <span style={{ fontSize: 13 }}>{nameA}</span>
      <input type="number" value={valueA} onChange={(e) => onChangeA(e.target.value)} style={{ width: 90 }} />
      <span style={{ fontSize: 13 }}>{nameB}</span>
      <input type="number" value={valueB} onChange={(e) => onChangeB(e.target.value)} style={{ width: 90 }} />
      <span>
        {isCustom && <span className="badge">自訂</span>}
        {!isCustom && isLive && <span className="badge" style={{ color: '#ffd60a', borderColor: '#ffd60a' }}>即時</span>}
      </span>
      <button onClick={onTrack} disabled={!isCustom} style={{ justifySelf: 'start' }}>{trackLabel}</button>
    </div>
  )
}

function Stat({ label, value, cls }) {
  return (
    <div>
      <div style={{ color: 'var(--muted)', fontSize: 12 }}>{label}</div>
      <div className={cls || ''} style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
    </div>
  )
}

const REBALANCE_PRESETS = [100, 75, 50, 25, 0]

function RebalanceCalc({ log, d }) {
  const [open, setOpen] = useState(true)
  const [ratioA, setRatioA] = useState(50) // % of total value targeted at symbol A; B is always 100-ratioA
  const holdA = d.holdings[log.symbol_a] || 0
  const holdB = d.holdings[log.symbol_b] || 0
  const pa = d.price_a
  const pb = d.price_b
  const ready = pa > 0 && pb > 0

  function setPctA(raw) {
    const n = Number(raw)
    if (Number.isNaN(n)) return
    setRatioA(Math.min(100, Math.max(0, n)))
  }

  let rows = null
  if (ready) {
    const totalValue = d.cash + holdA * pa + holdB * pb
    const targetA = (totalValue * (ratioA / 100)) / pa
    const targetB = (totalValue * (1 - ratioA / 100)) / pb
    const deltaA = targetA - holdA
    const deltaB = targetB - holdB
    rows = [
      { name: log.name_a, hold: holdA, price: pa, target: targetA, delta: deltaA },
      { name: log.name_b, hold: holdB, price: pb, target: targetB, delta: deltaB },
    ]
  }

  return (
    <div className="editor" style={{ marginBottom: 16 }}>
      <div
        className="row"
        style={{ justifyContent: 'space-between', cursor: 'pointer' }}
        onClick={() => setOpen((o) => !o)}
      >
        <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: open ? 8 : 0 }}>
          回歸目標比例試算（現金一併全數投入兩檔，僅供參考，不會建立交易紀錄；股價跟著上方「統計參考股價」走）
        </div>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{open ? '收合 ▲' : '展開 ▼'}</span>
      </div>

      {open && (
        <div className="row" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
          {REBALANCE_PRESETS.map((p) => (
            <button
              key={p}
              className={ratioA === p ? 'active' : ''}
              onClick={() => setRatioA(p)}
            >
              {p}/{100 - p}
            </button>
          ))}
          <span style={{ color: 'var(--muted)', fontSize: 13, marginLeft: 8 }}>自訂</span>
          <input type="number" min={0} max={100} value={ratioA} onChange={(e) => setPctA(e.target.value)} style={{ width: 70 }} />
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>{log.name_a} / </span>
          <input type="number" min={0} max={100} value={100 - ratioA} onChange={(e) => setPctA(100 - Number(e.target.value))} style={{ width: 70 }} />
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>{log.name_b}</span>
        </div>
      )}

      {open && ready && (
        <>
          <table style={{ marginBottom: 8 }}>
            <thead>
              <tr>
                <th></th>
                <th style={{ textAlign: 'right' }}>目前持股</th>
                <th style={{ textAlign: 'right' }}>目前市值</th>
                <th style={{ textAlign: 'right' }}>目標股數</th>
                <th style={{ textAlign: 'right' }}>應增減股數</th>
                <th style={{ textAlign: 'right' }}>應增減金額</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} style={{ cursor: 'default' }}>
                  <td>{r.name}</td>
                  <td style={{ textAlign: 'right' }}>{shareStr(r.hold)}</td>
                  <td style={{ textAlign: 'right' }}>{money(r.hold * r.price)}</td>
                  <td style={{ textAlign: 'right' }}>{shareStr(r.target)}</td>
                  <td style={{ textAlign: 'right' }} className={actionCls(r.delta)}>
                    {r.delta >= 0 ? '+' : ''}{shareStr(r.delta)}（{r.delta >= 0 ? '買進' : '賣出'}）
                  </td>
                  <td style={{ textAlign: 'right' }} className={actionCls(r.delta)}>
                    {r.delta >= 0 ? '+' : ''}{money(r.delta * r.price)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ color: 'var(--muted)', fontSize: 12 }}>
            試算基準：現金 {money(d.cash)} + {log.name_a} {shareStr(holdA)}股 + {log.name_b} {shareStr(holdB)}股，
            以你填的股價算出總市值後依 {ratioA}/{100 - ratioA} 比例分配、現金歸零。
          </div>
        </>
      )}
    </div>
  )
}
