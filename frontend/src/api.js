// Thin wrapper around the backend REST API. All paths go through the Vite
// dev proxy (/api -> http://localhost:8000).

const BASE = '/api'

async function req(path, options) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

const enc = encodeURIComponent

export const api = {
  listSymbols: ({ market, type, q, withQuote } = {}) => {
    const p = new URLSearchParams()
    if (market) p.set('market', market)
    if (type) p.set('type', type)
    if (q) p.set('q', q)
    if (withQuote) p.set('with_quote', 'true')
    const qs = p.toString()
    return req('/symbols' + (qs ? `?${qs}` : ''))
  },
  getSymbol: (symbol) => req(`/symbols/${enc(symbol)}`),
  getPrices: (symbol, range = '6mo', interval = '1d') =>
    req(`/symbols/${enc(symbol)}/prices?range=${enc(range)}&interval=${enc(interval)}`),
  updateSymbol: (symbol, interval = '1d') =>
    req(`/symbols/${enc(symbol)}/update?interval=${enc(interval)}`, { method: 'POST' }),
  getHomeIndices: () => req('/home/indices'),
  setHomeIndices: (symbols) =>
    req('/home/indices', { method: 'PUT', body: JSON.stringify({ symbols }) }),
  addSymbol: (body) => req('/symbols', { method: 'POST', body: JSON.stringify(body) }),
  updateAll: () => req('/update-all', { method: 'POST' }),
  getStrategies: () => req('/backtest/strategies'),
  runBacktest: (body) => req('/backtest', { method: 'POST', body: JSON.stringify(body) }),
  getPairStrategyConfig: () => req('/pair-strategy/config'),
  getPairStrategyDates: () => req('/pair-strategy/dates'),
  getPairStrategySignals: (date) =>
    req('/pair-strategy/signals' + (date ? `?date=${enc(date)}` : '')),
  updatePairStrategy: () => req('/pair-strategy/update', { method: 'POST' }),
  getPairStrategyV2Config: () => req('/pair-strategy-v2/config'),
  getPairStrategyV2Dates: () => req('/pair-strategy-v2/dates'),
  getPairStrategyV2Signals: (date) =>
    req('/pair-strategy-v2/signals' + (date ? `?date=${enc(date)}` : '')),
  getPairStrategyLiteConfig: () => req('/pair-strategy-lite/config'),
  getPairStrategyLiteDates: () => req('/pair-strategy-lite/dates'),
  getPairStrategyLiteSignals: (date) =>
    req('/pair-strategy-lite/signals' + (date ? `?date=${enc(date)}` : '')),
  getPairStrategyLiteLive: () => req('/pair-strategy-lite/live'),
  getPairStrategyLiteQuotes: (date) => req('/pair-strategy-lite/quotes' + (date ? `?date=${enc(date)}` : '')),
  getHoldings: () => req('/holdings'),
  getPairStrategyLiteIndexQuotes: (date) => req('/pair-strategy-lite/index-quotes' + (date ? `?date=${enc(date)}` : '')),
  getPairStrategyLiteOverrides: () => req('/pair-strategy-lite/overrides'),
  setPairStrategyLiteOverride: (pairKey, level, side) =>
    req(`/pair-strategy-lite/overrides/${enc(pairKey)}`, { method: 'PUT', body: JSON.stringify({ level, side }) }),
  clearPairStrategyLiteOverride: (pairKey) =>
    req(`/pair-strategy-lite/overrides/${enc(pairKey)}`, { method: 'DELETE' }),
  getTradeLogPairOptions: () => req('/trade-logs/pair-options'),
  listTradeLogs: () => req('/trade-logs'),
  createTradeLog: (body) => req('/trade-logs', { method: 'POST', body: JSON.stringify(body) }),
  getTradeLog: (id) => req(`/trade-logs/${id}`),
  deleteTradeLog: (id) => req(`/trade-logs/${id}`, { method: 'DELETE' }),
  updateTradeLog: (id, body) => req(`/trade-logs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  setTradeLogPrice: (id, body) => req(`/trade-logs/${id}/price`, { method: 'PUT', body: JSON.stringify(body) }),
  clearTradeLogPrice: (id) => req(`/trade-logs/${id}/price`, { method: 'DELETE' }),
  setTradeLogStartPrice: (id, body) => req(`/trade-logs/${id}/start-price`, { method: 'PUT', body: JSON.stringify(body) }),
  clearTradeLogStartPrice: (id) => req(`/trade-logs/${id}/start-price`, { method: 'DELETE' }),
  addTradeEntry: (id, body) => req(`/trade-logs/${id}/entries`, { method: 'POST', body: JSON.stringify(body) }),
  deleteTradeEntry: (id, entryId) => req(`/trade-logs/${id}/entries/${entryId}`, { method: 'DELETE' }),
  setTradeEntryIncluded: (id, entryId, included) =>
    req(`/trade-logs/${id}/entries/${entryId}`, { method: 'PATCH', body: JSON.stringify({ included }) }),
  getTrackedSymbols: () => req('/tracked-symbols'),
  addTrackedSymbol: (symbol) => req('/tracked-symbols', { method: 'POST', body: JSON.stringify({ symbol }) }),
  removeTrackedSymbol: (symbol) => req(`/tracked-symbols/${enc(symbol)}`, { method: 'DELETE' }),
  setTrackedPipHidden: (symbol, hidden) =>
    req(`/tracked-symbols/${enc(symbol)}/pip-hidden`, { method: 'PUT', body: JSON.stringify({ hidden }) }),
  setTrackedOrder: (symbols) => req('/tracked-symbols/order', { method: 'PUT', body: JSON.stringify({ symbols }) }),
}
