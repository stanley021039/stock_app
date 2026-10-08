// Renders a price change (absolute + percent) with up/down colouring.
export default function Quote({ quote, inline = false }) {
  if (!quote || quote.change == null) return <span className="flat">—</span>
  const up = quote.change > 0
  const down = quote.change < 0
  const cls = up ? 'up' : down ? 'down' : 'flat'
  const arrow = up ? '▲' : down ? '▼' : ''
  const chg = quote.change.toFixed(2)
  const pct = quote.change_pct != null ? quote.change_pct.toFixed(2) : '0.00'
  return (
    <span className={`${cls}${inline ? '' : ' chg'}`}>
      {arrow} {chg} ({pct}%)
    </span>
  )
}
