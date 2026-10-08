import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { NEXT_DAY, SignalRow } from '../components/PairStrategyShared.jsx'

// Same tab format as PairStrategy.jsx (v1) -- just a different dev/baseline
// formula under the hood. See backend/pair_strategy_v2.py's docstring.
// The "更新" button reuses v1's update endpoint: v2 watches the exact same
// 4 pairs' symbols, already kept fresh from there.
export default function PairStrategyV2() {
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
        const [cfg, d] = await Promise.all([api.getPairStrategyV2Config(), api.getPairStrategyV2Dates()])
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
      .getPairStrategyV2Signals(selectedDate === NEXT_DAY ? undefined : selectedDate)
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
      } else {
        const d = await api.getPairStrategyV2Dates()
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

  const dateSet = new Set(dates)
  const minDate = dates[dates.length - 1]
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
        <h2>配對再平衡策略 v2（基準點版）</h2>
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
          跟「配對策略」分頁監控同一批股票、同一套更新按鈕——按「更新」就是更新那批股票的收盤價，這裡只是換一種訊號算法在看。
          日期選擇器一樣：留空＝預測下一交易日，選某個實際日期則顯示「進場那天要看的門檻(用前一天收盤算)」+「那天實際發生了什麼」。
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
        <h3 style={{ marginBottom: 8 }}>策略詳情（跟「配對策略」的差異）</h3>
        <div style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.7 }}>
          <p>
            進場/回流機制跟「配對策略」分頁完全一樣（分級進場、每級最多觸發一次、回流時全部歸零50/50）——
            <b>唯一的差別是 dev 怎麼算</b>。
          </p>
          <p>
            <b>配對策略(v1)</b>：<code>dev_X(t) = 收盤價_X(t) / MA_X(t) − 1</code>，MA_X是「過去N天含當天」的移動平均，
            每天都會跟著最新價格重新平滑——本質是均值回歸。
          </p>
          <p>
            <b>這個分頁(v2)</b>：<code>dev_X(t) = 收盤價_X(t) / 基準_X(t) − 1</code>，
            <code>基準_X(t)</code> 是「N天視窗裡最舊的k天」的均價（例如MA60、基準取最舊10天，就是比較今天收盤價跟大約55~60天前那一小段價位）。
            這個基準每天還是會隨視窗滑動重新計算，但拿來比較的是「大約N天前」而不是「最近N天的平均」——比較接近動能/N日報酬率，不是均值回歸。
          </p>
          <p>
            <code>diff(t) = dev_A(t) − dev_B(t)</code>，之後的分級進場/回流判斷跟v1完全相同。
          </p>
          <p>
            <b>參數怎麼選的</b>：對「配對策略」分頁現行的4對股票，各自額外跑一次(MA,基準天數)網格搜索
            （基準天數∈{'{'}1,3,5,7,10{'}'}），挑出比v1原本的均線版更好（或至少同等）的一格才列在下表；
            記憶體雙雄、封測雙雄在這個算法下全面優於v1，被動元件雙雄、功率元件雙雄則是超額報酬較高但Sharpe較低、交易次數較多的取捨。
          </p>

          {config && (
            <div style={{ overflowX: 'auto', margin: '12px 0' }}>
              <table>
                <thead>
                  <tr>
                    <th>股對</th>
                    <th>MA</th>
                    <th>基準天數</th>
                    <th>分級</th>
                    <th style={{ textAlign: 'right' }}>超額pp</th>
                    <th style={{ textAlign: 'right' }}>End勝率</th>
                    <th style={{ textAlign: 'right' }}>1年勝率</th>
                    <th style={{ textAlign: 'right' }}>Sharpe</th>
                    <th style={{ textAlign: 'right' }}>最大回撤</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(config.pairs).map(([key, p]) => (
                    <tr key={key}>
                      <td>{p.label}({p.nameA}/{p.nameB})</td>
                      <td>{p.ma}</td>
                      <td>{p.baseline_days}</td>
                      <td>{p.tiers.map((t) => (t * 100).toFixed(1)).join('/')}% (各一次，每級賣{(p.sell_fraction * 100).toFixed(0)}%)</td>
                      <td style={{ textAlign: 'right' }}>{p.excess_pp >= 0 ? '+' : ''}{p.excess_pp.toFixed(1)}</td>
                      <td style={{ textAlign: 'right' }}>{p.end_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.one_year_win_rate.toFixed(1)}%</td>
                      <td style={{ textAlign: 'right' }}>{p.sharpe.toFixed(2)}</td>
                      <td style={{ textAlign: 'right' }}>{p.max_dd.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p>
            重要提醒：這裡只是研究階段的<b>平行觀察分頁</b>，不是正式採用的策略——「配對策略」分頁維持原本的均線版本不變。
            要不要正式改用這套算法（全部或個別股對），要等這裡實際觀察一段時間、你確認後才會動到現行策略。
          </p>
        </div>
      </div>
    </div>
  )
}
