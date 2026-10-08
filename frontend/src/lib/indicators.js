// Client-side technical indicators computed from the price bars.

// Simple moving average. Returns array aligned to input (null until enough bars).
export function sma(values, period) {
  const out = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

// Taiwan-style stochastic KD (alpha = 1/smooth, seeded at 50).
// highs/lows/closes are parallel arrays. Returns { k:[], d:[] }.
export function kd(highs, lows, closes, n = 9, kSmooth = 3, dSmooth = 3) {
  const len = closes.length
  const k = new Array(len)
  const d = new Array(len)
  let prevK = 50
  let prevD = 50
  for (let i = 0; i < len; i++) {
    const from = Math.max(0, i - n + 1)
    let lo = Infinity
    let hi = -Infinity
    for (let j = from; j <= i; j++) {
      if (lows[j] < lo) lo = lows[j]
      if (highs[j] > hi) hi = highs[j]
    }
    const rsv = hi === lo ? 50 : ((closes[i] - lo) / (hi - lo)) * 100
    prevK = prevK + (1 / kSmooth) * (rsv - prevK)
    prevD = prevD + (1 / dSmooth) * (prevK - prevD)
    k[i] = prevK
    d[i] = prevD
  }
  return { k, d }
}
