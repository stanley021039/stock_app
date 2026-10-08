import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api.js'
import { TriggerList } from './LiteTriggers.jsx'
import { useDragReorder } from '../lib/useDragReorder.js'

const POLL_MS = 15000

const fmtPrice = (x) => (x == null ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: 2 }))
const fmtChangePct = (x) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}%`)
const changeCls = (x) => (x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat')

// Header button that opens a Document Picture-in-Picture mini window
// (Chrome/Edge only) -- always on top, even over other apps. Lives in the
// app header rather than any one page so it keeps working whichever tab is
// open; it does its own polling, and only while the window is open. The
// PiP window has no script of its own: content is rendered into it from
// here via a portal.
export default function PipLauncher() {
  const supported = typeof window !== 'undefined' && 'documentPictureInPicture' in window
  const [pipWindow, setPipWindow] = useState(null)
  const [tab, setTab] = useState('quotes')
  const [trackedRows, setTrackedRows] = useState([])
  const [live, setLive] = useState(null)
  const [lastPollAt, setLastPollAt] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!pipWindow) return
    let cancelled = false
    async function poll() {
      try {
        const [rows, lv] = await Promise.all([api.getTrackedSymbols(), api.getPairStrategyLiteLive()])
        if (cancelled) return
        setTrackedRows(rows)
        setLive(lv)
        setLastPollAt(new Date())
        setError(null)
      } catch (e) {
        if (!cancelled) setError(e.message)
      }
    }
    poll()
    const t = setInterval(poll, POLL_MS)
    return () => { cancelled = true; clearInterval(t) }
  }, [pipWindow])

  // Close it if the whole app unmounts (e.g. HMR), so it isn't orphaned.
  useEffect(() => () => pipWindow?.close(), [pipWindow])

  // The PiP only lists non-hidden symbols, so a drag there reorders just
  // those -- slot them back into the full list in place, leaving each
  // hidden symbol where it was instead of shoving it to the end.
  async function reorderTracked(nextVisible) {
    const queue = [...nextVisible]
    const next = trackedRows.map((r) => (r.pip_hidden ? r : queue.shift()))
    setTrackedRows(next) // optimistic
    try {
      setTrackedRows(await api.setTrackedOrder(next.map((r) => r.symbol)))
    } catch (e) {
      setError(e.message)
    }
  }

  async function open() {
    try {
      const w = await window.documentPictureInPicture.requestWindow({ width: 300, height: 420 })
      // Fresh document -- copy the app's stylesheets over so the panel
      // looks the same (CSS vars, .up/.down colors, fonts).
      for (const sheet of document.styleSheets) {
        try {
          const style = w.document.createElement('style')
          style.textContent = [...sheet.cssRules].map((r) => r.cssText).join('\n')
          w.document.head.appendChild(style)
        } catch {
          if (sheet.href) {
            const link = w.document.createElement('link')
            link.rel = 'stylesheet'
            link.href = sheet.href
            w.document.head.appendChild(link)
          }
        }
      }
      w.document.title = '看盤小視窗'
      w.document.body.style.margin = '0'
      w.addEventListener('pagehide', () => setPipWindow(null))
      setPipWindow(w)
    } catch (e) {
      setError(e.message)
    }
  }

  if (!supported) return null

  return (
    <>
      <button
        onClick={pipWindow ? () => pipWindow.close() : open}
        className={pipWindow ? 'active' : ''}
        title="開一個永遠在最上層的小視窗（切到別的程式也看得到）"
      >
        {pipWindow ? '關閉子母視窗' : '子母視窗'}
      </button>
      {pipWindow && createPortal(
        <PipPanel
          tab={tab}
          onTab={setTab}
          trackedRows={trackedRows}
          onReorder={reorderTracked}
          live={live}
          lastPollAt={lastPollAt}
          error={error}
        />,
        pipWindow.document.body,
      )}
    </>
  )
}

function PipPanel({ tab, onTab, trackedRows, onReorder, live, lastPollAt, error }) {
  const liveResults = live?.results ?? []
  const triggerCount = liveResults.filter((r) => r.entered_today || r.reset_today).length
  const tabStyle = (active) => ({
    flex: 1, padding: '4px 0', fontSize: 12,
    ...(active ? {} : { background: 'transparent', color: 'var(--muted)' }),
  })
  const status = error
    ? `⚠ ${error}`
    : live && !live.quote_service_ok
      ? '⚠ 即時報價服務連不上'
      : live?.market_open ? '盤中・每15秒更新' : '非交易時間'
  return (
    <div style={{
      padding: 10, minHeight: '100vh', boxSizing: 'border-box',
      borderLeft: `4px solid ${triggerCount ? '#30a46c' : 'var(--border)'}`,
    }}>
      <div className="row" style={{ gap: 4, marginBottom: 8, flexWrap: 'nowrap' }}>
        <button className={tab === 'quotes' ? 'active' : ''} style={tabStyle(tab === 'quotes')} onClick={() => onTab('quotes')}>
          即時漲跌
        </button>
        <button className={tab === 'signals' ? 'active' : ''} style={tabStyle(tab === 'signals')} onClick={() => onTab('signals')}>
          觸發訊號{triggerCount > 0 && <span className="up"> ({triggerCount})</span>}
        </button>
      </div>

      {tab === 'quotes' ? <TrackedQuoteList rows={trackedRows.filter((r) => !r.pip_hidden)} onReorder={onReorder} /> : <TriggerList liveResults={liveResults} />}

      <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 10 }}>
        {status}
        {lastPollAt && `・${lastPollAt.toLocaleTimeString('zh-TW', { hour12: false })}`}
      </div>
    </div>
  )
}

// "南亞科 Nanya Tech" -> "南亞科": keep just the Chinese name when there is
// one -- the symbols table stores both for search.
const shortName = (name) => {
  const head = (name || '').split(' ')[0]
  return /[一-鿿]/.test(head) ? head : name
}

function TrackedQuoteList({ rows, onReorder }) {
  const reorder = useDragReorder(rows, (r) => r.symbol, onReorder)
  if (rows.length === 0) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>沒有追蹤中的股票</div>
  return (
    <table style={{ width: '100%', fontSize: 13 }}>
      <tbody>
        {rows.map((r) => {
          const pct = r.quote?.change_pct
          return (
            <tr key={r.symbol} {...reorder.rowProps(r)}>
              <td {...reorder.handleProps(r)} style={{ ...reorder.handleProps(r).style, padding: '3px 2px' }}>⋮⋮</td>
              <td style={{ padding: '3px 4px' }}>{shortName(r.name)}</td>
              <td style={{ padding: '3px 4px', textAlign: 'right' }}>{fmtPrice(r.quote?.price)}</td>
              <td style={{ padding: '3px 4px', textAlign: 'right', width: 64 }} className={changeCls(pct)}>
                {fmtChangePct(pct)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
