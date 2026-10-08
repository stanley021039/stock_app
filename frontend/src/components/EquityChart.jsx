import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineSeries } from 'lightweight-charts'

// Plots one or more equity curves on a shared time axis.
//   series: [{ name, color, data: [{date, value}] }]
export default function EquityChart({ series = [], height = 380 }) {
  const containerRef = useRef(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8b949e',
        fontFamily: 'system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(42,49,64,0.6)' },
        horzLines: { color: 'rgba(42,49,64,0.6)' },
      },
      rightPriceScale: { borderColor: '#2a3140' },
      timeScale: { borderColor: '#2a3140', timeVisible: false },
      crosshair: { mode: 0 },
    })

    for (const s of series) {
      const line = chart.addSeries(LineSeries, {
        color: s.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      line.setData((s.data || []).map((p) => ({ time: p.date, value: p.value })))
    }

    chart.timeScale().fitContent()
    let lastW = el.clientWidth
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth
      if (w && w !== lastW) {
        lastW = w
        chart.applyOptions({ width: w })
      }
    })
    ro.observe(el)
    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [series, height])

  return <div ref={containerRef} style={{ width: '100%' }} />
}
