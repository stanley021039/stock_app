import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { NEXT_DAY, SignalRow } from '../components/PairStrategyShared.jsx'

export default function PairStrategy() {
  const [config, setConfig] = useState(null)
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState(NEXT_DAY)
  const [signals, setSignals] = useState(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [notice, setNotice] = useState(null)
  const [dateWarning, setDateWarning] = useState(null)
  const [error, setError] = useState(null)
  const [updatePopup, setUpdatePopup] = useState(null)

  useEffect(() => {
    ;(async () => {
      try {
        const [cfg, d] = await Promise.all([api.getPairStrategyConfig(), api.getPairStrategyDates()])
        setConfig(cfg)
        setDates(d.dates)
      } catch (e) {
        setError(e.message)
      }
    })()
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .getPairStrategySignals(selectedDate === NEXT_DAY ? undefined : selectedDate)
      .then((r) => setSignals(r.signals))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedDate])

  async function handleUpdate() {
    setUpdating(true)
    setNotice(null)
    setDateWarning(null)
    setError(null)
    try {
      const r = await api.updatePairStrategy()
      if (!r.updated) {
        if (r.reason === 'weekend') setNotice('今天是週末，非交易日')
        else if (r.reason === 'market not closed yet (13:30 Taipei)') setNotice('今天還沒收盤（13:30前），暫不更新')
        // reason === 'already up to date' -> nothing missing, stay silent
      } else {
        const d = await api.getPairStrategyDates()
        setDates(d.dates)
        setSelectedDate(NEXT_DAY)
        showUpdatePopup(`已更新 ${r.succeeded}/${r.attempted}`)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setUpdating(false)
    }
  }

  function showUpdatePopup(text) {
    setUpdatePopup(text)
    setTimeout(() => setUpdatePopup(null), 5000)
  }

  const excludedList = useMemo(
    () => (config ? Object.values(config.excluded) : []),
    [config],
  )

  const dateSet = useMemo(() => new Set(dates), [dates])
  const minDate = dates[dates.length - 1] // dates is sorted newest-first
  const maxDate = dates[0]

  function handleDateInput(value) {
    setDateWarning(null)
    if (!value) {
      setSelectedDate(NEXT_DAY)
      return
    }
    if (!dateSet.has(value)) {
      setDateWarning(`${value} 不是交易日，或超出可查詢範圍（最近${dates.length}個交易日：${minDate}～${maxDate}），請重新選擇`)
      return
    }
    setSelectedDate(value)
  }

  return (
    <div>
      {updatePopup && (
        <div
          style={{
            position: 'fixed', top: 70, right: 24, zIndex: 100,
            background: 'var(--panel-2)', border: '1px solid var(--accent)', borderRadius: 8,
            padding: '10px 16px', fontSize: 13, boxShadow: '0 4px 16px rgba(0,0,0,.5)',
          }}
        >
          {updatePopup}
        </div>
      )}

      <div className="section-title">
        <h2>配對再平衡策略 Pair Strategy</h2>
      </div>

      <div className="editor" style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 12, alignItems: 'center' }}>
          <button className="active" onClick={handleUpdate} disabled={updating}>
            {updating ? '更新中…' : '⟳ 更新'}
          </button>

          <label style={{ color: 'var(--muted)', fontSize: 13 }}>日期</label>
          <input
            type="date"
            value={selectedDate === NEXT_DAY ? '' : selectedDate}
            min={minDate}
            max={maxDate}
            onChange={(e) => handleDateInput(e.target.value)}
          />
          <button onClick={() => handleDateInput(maxDate)} disabled={!maxDate}>今天</button>
          <button onClick={() => handleDateInput('')}>明天</button>

          {loading && <span style={{ color: 'var(--muted)', fontSize: 13 }}>載入中…</span>}
          {notice && <span className="toast">{notice}</span>}
          {dateWarning && <span className="toast err">{dateWarning}</span>}
          {error && <span className="toast err">{error}</span>}
        </div>
        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
          按下去就檢查所有股對是否已收盤(13:30後)且有缺最新收盤價，有缺才會去抓，抓到才會跳出更新結果；沒有缺的話什麼都不會發生。
          日期選擇器純粹用來瀏覽：留空＝預測下一交易日，選某個實際日期則顯示「進場那天要看的門檻(用前一天收盤算)」+「那天實際發生了什麼」。
        </div>
      </div>

      {signals && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>A標的</th>
                <th>B標的</th>
                <th>訊號區間(A-B)</th>
                <th>加碼狀態</th>
                <th>當日實際結果</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <SignalRow key={s.key} s={s} />
              ))}
            </tbody>
          </table>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
            數線說明：每一級門檻都各自標一個刻度——紅側＝買A、綠側＝買B，粗刻度是下一個還沒觸發的級別，
            淡色刻度是這次未平倉期間已經觸發過的級別（滑鼠移到刻度上可看該級的細節）；亮色豎線＝目前A-B差值所在位置；
            橙色刻度＋色帶＝回流(平倉)門檻，色帶長度是「目前位置離回流還有多遠」，只有未平倉時才會出現，
            即使所有級別都已觸發也一樣會標出來。
          </div>
        </div>
      )}

      <div style={{ marginTop: 40, borderTop: '1px solid var(--border)', paddingTop: 20 }}>
        <h3 style={{ marginBottom: 8 }}>策略詳情</h3>
        <div style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.7 }}>
          <p>
            <code>dev_X(t) = 收盤價_X(t) / MA_X(t) − 1</code>（MA_X = 過去N天含當天的收盤均價，N依股對而定）；
            <code>diff(t) = dev_A(t) − dev_B(t)</code>。
          </p>
          <p>
            <b>分級進場</b>：一組由小到大的門檻階梯，每一級在同一次未平倉期間內最多只會觸發<b>一次</b>
            （超過最高一級不再加碼）。<code>|diff(t)|</code> 每突破階梯上的一個新級別，就賣出偏離較高那邊
            「目前持股市值」的一定比例，全數(扣手續費後)買進另一邊，標記為未平倉。用意是只在真正大幅偏離時才逐步加碼，
            比單一門檻「只要沒回流、隔天又超標就再賣一次」更節制。
          </p>
          <p>
            <b>回流(reset)</b>：僅在「目前有未平倉部位」時檢查——若 <code>diff(t-1) × diff(t) &lt; 0</code>
            （正負號翻轉/穿越0），不論當下差距多大，直接把兩邊市值強制拉回50/50，解除未平倉狀態，
            同時把所有已觸發的級別重設為未觸發。
          </p>
          <p>每天判斷順序：先檢查回流，再檢查新進場——兩件事可能同一天都發生。</p>
          <p>
            資金：期初100萬、50/50起始；買進手續費0.08%、賣出手續費0.08%、賣出證交稅0.3%；可零股交易；
            不做除權息調整；比較基準是50/50買進後永不再平衡的buy&amp;hold。
          </p>
          <p>
            <b>篩選規則</b>：對每組股對先跑單一門檻的完整(MA,門檻)網格（MA∈{'{'}3,5,7,10,15,30,60,90{'}'}、
            門檻∈{'{'}4,5,6,7,8,12{'}'}%），再對同一批股對額外跑分級進場的(MA,基準門檻)網格（分級＝基準門檻的
            1/1.5/2/2.5/3/3.5倍、每級賣30%），兩種機制個別找出「勝率/超額報酬/Sharpe/回撤」最平衡的一格，
            股對層級再比較兩種機制哪個更好、採用較優的一種，最終要求該格的 End勝率(滾動、抱到資料結束) ≥ 85%
            且超額報酬為正，兩個條件同時滿足才留下。
          </p>

          {config && (
            <div style={{ overflowX: 'auto', margin: '12px 0' }}>
              <table>
                <thead>
                  <tr>
                    <th>股對</th>
                    <th>MA</th>
                    <th>門檻 / 分級</th>
                    <th style={{ textAlign: 'right' }}>倍數比</th>
                    <th style={{ textAlign: 'right' }}>IR</th>
                    <th style={{ textAlign: 'right' }}>End勝率</th>
                    <th style={{ textAlign: 'right' }}>1年勝率</th>
                    <th style={{ textAlign: 'right' }}>超額pp</th>
                    <th style={{ textAlign: 'right' }}>最大回撤</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(config.pairs).map(([key, p]) => (
                    <tr key={key}>
                      <td>{p.label}({p.nameA}/{p.nameB})</td>
                      <td>{p.ma}</td>
                      <td>
                        {p.engine === 'tiered'
                          ? `${p.tiers.map((t) => (t * 100).toFixed(1)).join('/')}% (各一次，每級賣${(p.sell_fraction * 100).toFixed(0)}%)`
                          : `${(p.trigger * 100).toFixed(0)}%`}
                      </td>
                      <td style={{ textAlign: 'right' }}>{p.bh_ratio.toFixed(2)}x</td>
                      <td style={{ textAlign: 'right' }}>{p.ir.toFixed(2)}</td>
                      <td style={{ textAlign: 'right' }}>{p.end_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.one_year_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.excess_pp >= 0 ? '+' : ''}{p.excess_pp.toFixed(1)}</td>
                      <td style={{ textAlign: 'right' }}>{p.max_dd.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {excludedList.length > 0 && (
            <p>
              <b>被排除、目前不交易的股對</b>：
              {excludedList.map((e, i) => (
                <span key={i}>
                  {i > 0 && '；'}
                  {e.label}({e.nameA}/{e.nameB})：{e.reason}
                </span>
              ))}
            </p>
          )}
          <p>
            重要提醒：用的是「End勝率」不是「1年勝率」篩的——有些股對是「長期抱到底會贏，但不保證任何一年都穩」的類型，
            上表也同時列出1年滾動勝率供對照。沒有統一的「最佳MA天數」，每組股對的最佳參數都是個別網格搜索出來的結果。
          </p>
        </div>
      </div>
    </div>
  )
}
