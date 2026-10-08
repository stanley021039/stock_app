import { Routes, Route, Link, NavLink } from 'react-router-dom'
import Home from './pages/Home.jsx'
import StockPage from './pages/StockPage.jsx'
import Backtest from './pages/Backtest.jsx'
import PairStrategyLite from './pages/PairStrategyLite.jsx'
import TradeLog from './pages/TradeLog.jsx'
import TradeLogDetail from './pages/TradeLogDetail.jsx'
import TrackedSymbols from './pages/TrackedSymbols.jsx'
import Holdings from './pages/Holdings.jsx'
import PipLauncher from './components/PipLauncher.jsx'

export default function App() {
  return (
    <>
      <header className="app-header">
        <div className="brand">
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20 }}>📈</span>
            <h1>台美股看盤</h1>
          </Link>
        </div>
        <nav className="row" style={{ gap: 4 }}>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>首頁</NavLink>
          <NavLink to="/backtest" className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>回測</NavLink>
          <NavLink to="/pair-strategy-lite" className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>配對策略</NavLink>
          <NavLink to="/trade-log" className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>真實交易記錄</NavLink>
          <NavLink to="/holdings" className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>庫存</NavLink>
          <NavLink to="/tracked-symbols" className={({ isActive }) => (isActive ? 'btn active' : 'btn')}>報價追蹤</NavLink>
        </nav>
        <div style={{ marginLeft: 'auto' }}>
          <PipLauncher />
        </div>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/stock/:symbol" element={<StockPage />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/pair-strategy-lite" element={<PairStrategyLite />} />
          <Route path="/trade-log" element={<TradeLog />} />
          <Route path="/trade-log/:id" element={<TradeLogDetail />} />
          <Route path="/holdings" element={<Holdings />} />
          <Route path="/tracked-symbols" element={<TrackedSymbols />} />
        </Routes>
      </main>
    </>
  )
}
