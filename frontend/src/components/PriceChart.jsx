import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  AreaSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts'
import { sma, kd } from '../lib/indicators.js'

const MA_COLORS = { 5: '#f2c94c', 10: '#f2994a', 20: '#f2994a', 60: '#bb6bd9', 120: '#56ccf2' }

// OHLC chart (lightweight-charts v5) with optional MA overlays and a KD pane.
//   kind="candle" -> candlestick + volume; kind="area" -> close-price area
//   maList: array of MA periods to overlay (e.g. [5,20,60])
//   showKD: render KD(9,3,3) in a second pane
export default function PriceChart({ data, kind = 'candle', maList = [], showKD = false, intraday = false, height = 460 }) {
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
      timeScale: { borderColor: '#2a3140', timeVisible: intraday, secondsVisible: false },
      crosshair: { mode: 0 },
    })

    const bars = (data || []).filter((r) => r.close != null)
    const times = bars.map((r) => r.time)
    const closes = bars.map((r) => r.close)

    if (kind === 'area') {
      const series = chart.addSeries(AreaSeries, {
        lineColor: '#2f81f7',
        topColor: 'rgba(47,129,247,0.4)',
        bottomColor: 'rgba(47,129,247,0.02)',
        lineWidth: 2,
      })
      series.setData(bars.map((r) => ({ time: r.time, value: r.close })))
    } else {
      const candles = chart.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderUpColor: '#26a69a',
        borderDownColor: '#ef5350',
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
      })
      candles.setData(
        bars.map((r) => ({ time: r.time, open: r.open, high: r.high, low: r.low, close: r.close })),
      )

      const vol = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      })
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      vol.setData(
        bars
          .filter((r) => r.volume != null)
          .map((r) => ({
            time: r.time,
            value: r.volume,
            color: r.close >= r.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)',
          })),
      )
    }

    // MA overlays (price pane)
    for (const period of maList) {
      const arr = sma(closes, period)
      const line = chart.addSeries(LineSeries, {
        color: MA_COLORS[period] || '#9aa4b2',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      line.setData(
        arr.map((v, i) => (v == null ? null : { time: times[i], value: v })).filter(Boolean),
      )
    }

    // KD sub-pane
    if (showKD && bars.length) {
      const highs = bars.map((r) => r.high)
      const lows = bars.map((r) => r.low)
      const { k, d } = kd(highs, lows, closes)
      const kLine = chart.addSeries(LineSeries, { color: '#f2994a', lineWidth: 1, priceLineVisible: false }, 1)
      const dLine = chart.addSeries(LineSeries, { color: '#56ccf2', lineWidth: 1, priceLineVisible: false }, 1)
      kLine.setData(k.map((v, i) => ({ time: times[i], value: v })))
      dLine.setData(d.map((v, i) => ({ time: times[i], value: v })))
      try {
        const panes = chart.panes()
        if (panes[0]) panes[0].setStretchFactor(3)
        if (panes[1]) panes[1].setStretchFactor(1)
      } catch {
        /* pane sizing is best-effort */
      }
    }

    chart.timeScale().fitContent()

    // Only react to real width changes — avoids a ResizeObserver feedback loop
    // when a scrollbar appears/disappears (which would repaint endlessly).
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
  }, [data, kind, maList, showKD, intraday, height])

  return <div ref={containerRef} style={{ width: '100%' }} />
}
