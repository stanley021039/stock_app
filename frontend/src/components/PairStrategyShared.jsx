// Shared building blocks for the pair-strategy tabs (v1: MA-deviation vs a
// rolling average; v2: MA-deviation vs a fixed baseline from ~N days ago).
// Both share identical tiered entry/reset mechanics and the same threshold
// bar/tick visualization -- only the backend's dev/baseline formula and
// the resulting numbers differ.
export const pct = (x, digits = 2) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(digits)}%`)

export const NEXT_DAY = '' // sentinel selected-date value meaning "predict next trading day"

export function SignalRow({ s, extraCell }) {
  if (s.error) {
    return (
      <tr>
        <td colSpan={extraCell ? 7 : 6}>{s.label}：{s.error}</td>
      </tr>
    )
  }

  const isOpen = s.is_open_before
  const tiltSide = s.basis_diff > 0 ? s.nameB : s.nameA // diff>0 means A was sold into B on entry
  const entriesForDisplay = s.outcome_known ? s.entries_since_reset_after : s.entries_since_reset
  const tierSuffix = s.engine === 'tiered' ? `/${s.tier_count}級` : '次'
  const maxed = s.engine === 'tiered' && s.maxed_out

  return (
    <tr>
      {extraCell}
      <td>
        <InfoIcon s={s} />
      </td>
      <td>{s.nameA}</td>
      <td>{s.nameB}</td>
      <td>
        <ThresholdBar s={s} />
      </td>
      <td>
        {isOpen ? (
          <>
            🟠 加碼在{tiltSide} {entriesForDisplay}{tierSuffix}
            {maxed && <div style={{ color: 'var(--muted)', fontSize: 11 }}>已達最高級，等待回流</div>}
          </>
        ) : (
          <span style={{ color: 'var(--muted)' }}>⚪ 空手</span>
        )}
      </td>
      <td>
        {s.outcome_known ? (
          <>
            實際diff：{pct(s.actual_diff)}
            <div style={{ color: 'var(--muted)', fontSize: 12 }}>
              {s.entered_today && s.reset_today
                ? '✅ 回流平倉 + 新進場'
                : s.entered_today
                  ? '✅ 觸發新進場'
                  : s.reset_today
                    ? '✅ 觸發回流平倉'
                    : '未觸發'}
            </div>
          </>
        ) : (
          <span style={{ color: 'var(--muted)' }}>尚未收盤，無結果</span>
        )}
      </td>
    </tr>
  )
}

export function InfoIcon({ s }) {
  return (
    <span className="info-icon">
      !
      <span className="info-tooltip">
        <div><b>{s.label}</b>（{s.nameA}/{s.nameB}）</div>
        {s.engine === 'tiered' ? (
          <div>
            參數：MA{s.ma}{s.baseline_days != null ? `(基準取最舊${s.baseline_days}天)` : ''}
            {' '}+ 分級{s.tiers.map((t) => (t * 100).toFixed(1)).join('/')}%（各一次，每級賣{(s.sell_fraction * 100).toFixed(0)}%）
          </div>
        ) : s.engine === 'band' ? (
          <div>
            參數：MA{s.ma} + 門檻{s.tiers.map((t) => (t * 100).toFixed(1)).join('/')}%
            （弱勢股權重 {s.band_weights.map((w) => (w * 100).toFixed(0)).join('/')}%；
            T2只進不退、減碼只有一次，變號才回50/50）
          </div>
        ) : (
          <div>參數：MA{s.ma} + 門檻{(s.trigger * 100).toFixed(0)}%</div>
        )}
        {/* bh_ratio/ir are the primary read; pp and Sharpe are kept below as
            secondary since they conflate the pair's own beta with the
            strategy's edge. Only v1 carries them so far -- v2/lite tabs
            simply fall through to the pp/Sharpe lines. */}
        {s.bh_ratio != null && <div><b>終值倍數比(策略÷長抱)：{s.bh_ratio.toFixed(2)}x</b></div>}
        {s.ir != null && <div><b>IR(超額報酬風險調整)：{s.ir.toFixed(2)}</b></div>}
        <div>End勝率(滾動抱到資料結束)：{s.end_win_rate.toFixed(1)}%</div>
        <div>1年滾動勝率：{s.one_year_win_rate.toFixed(1)}%</div>
        <div>回測超額報酬：{s.excess_pp >= 0 ? '+' : ''}{s.excess_pp.toFixed(1)}pp</div>
        <div>Sharpe：{s.sharpe.toFixed(2)}</div>
        <div>最大回撤：{s.max_dd.toFixed(1)}%</div>
        {s.n_trades != null && <div>交易次數：{s.n_trades}筆{s.turnover != null && `｜換手 ${s.turnover.toFixed(1)}x`}</div>}
        {s.costs_included && <div style={{ color: 'var(--muted)' }}>回測已計入手續費+證交稅</div>}
        {s.backtest_start && <div>回測區間：{s.backtest_start} ~ {s.backtest_end}</div>}
      </span>
    </span>
  )
}

export const BAR_W = 320
const BAR_H = 54
const BAR_Y = 28
const BAR_H_TRACK = 8

// Horizontal number-line spanning the whole tier ladder (or the single
// flat trigger, for a "single"-engine pair). Unlike the old design, the
// axis IS the diff value itself (devA - devB, same units as curDiff) --
// tier ticks sit at the pair's own fixed +-tier thresholds, reset always
// sits at exactly 0, and the current/live markers plot at their own diff
// values directly. No price-move conversion, no per-day-shifting basis --
// every mark on this bar means the same thing in the same units.
//
// Purely a "signal" display -- lite's manual position override (see
// PairStrategyLite.jsx's PositionBar) is a separate concept shown in its
// own bar underneath, not layered into this one.
//
// hideCaption skips the trailing text line (exported separately below as
// ThresholdBarCaption) for callers that want to reposition it -- lite
// renders it after its own PositionBar instead of directly under the
// signal svg.
export function ThresholdBar({ s, liveDiff, hideCaption }) {
  // entry_high (along with tier_marks/trigger's underlying threshold data)
  // is only null for the earliest date in history, where there's no prior
  // day to have computed a threshold from at all -- curDiff itself can
  // still be non-null there (the actual diff still exists), so this can't
  // be replaced by a curDiff==null check.
  if (s.entry_high == null) {
    return <span style={{ color: 'var(--muted)' }}>—（此為最早一筆資料，無前一天可算門檻）</span>
  }
  const curDiff = s.outcome_known ? s.actual_diff : s.basis_diff

  const marks = s.tier_marks
    ? s.tier_marks.map((m) => ({ tier: m.tier, fired: m.fired }))
    : [{ tier: s.trigger, fired: s.is_open_before }]
  const widestTier = marks[marks.length - 1].tier
  const lo = -widestTier
  const hi = widestTier
  const span = hi - lo || 1
  const toX = (v) => ((Math.max(lo, Math.min(hi, v)) - lo) / span) * BAR_W

  const curX = toX(curDiff)
  const isOpen = s.is_open_before
  const resetX = toX(0) // reset always fires exactly at diff=0, by definition
  const liveX = liveDiff != null ? toX(liveDiff) : null
  const firedCount = marks.filter((m) => m.fired).length
  const nextIdx = marks.findIndex((m) => !m.fired)
  // m.fired/nextIdx only describe the CONTINUING direction (the one
  // matching curDiff's current sign) -- a sign flip always resets first,
  // so the OTHER side has never fired anything this episode and its own
  // next level is always tier[0], regardless of how far the continuing
  // side has progressed.
  const highIsContinuing = curDiff >= 0

  const gradId = `grad-${s.key}`
  const MARKER_COLOR = '#4f8cff'

  return (
    <div>
      <svg width={BAR_W} height={BAR_H} viewBox={`0 0 ${BAR_W} ${BAR_H}`} style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#e5484d" />
            <stop offset="50%" stopColor="#8a8f98" />
            <stop offset="100%" stopColor="#30a46c" />
          </linearGradient>
        </defs>

        <rect x={0} y={BAR_Y} width={BAR_W} height={BAR_H_TRACK} rx={3} fill={`url(#${gradId})`} opacity={0.8} />

        {/* every level's buy-A tick (left/red side) and buy-B tick (right/green side).
            The band engine's exit rule is asymmetric (see pair_strategy_lite.py's
            transition table): only the innermost tier (T1) is also an exit line --
            the outermost (T2) is entry-only, breaking back below it does nothing. */}
        {marks.map((m, i) => {
          const lowFired = highIsContinuing ? false : m.fired
          const highFired = highIsContinuing ? m.fired : false
          const lowNext = highIsContinuing ? i === 0 : i === nextIdx
          const highNext = highIsContinuing ? i === nextIdx : i === 0
          const exitNote = s.engine === 'band' ? (i === marks.length - 1 ? '（只進不退）' : '（進場/退場線）') : ''
          return (
            <g key={i}>
              <TickMark
                x={toX(-m.tier)} height={lowNext ? 9 : 5} stroke="#e5484d" strokeWidth={lowNext ? 2.5 : 1.5}
                opacity={lowFired ? 0.45 : 1}
                label={`買${s.nameA}：第${i + 1}級 → ${pct(-m.tier, 1)}${exitNote}${lowFired ? '（已觸發）' : ''}`}
              />
              <TickMark
                x={toX(m.tier)} height={highNext ? 9 : 5} stroke="#30a46c" strokeWidth={highNext ? 2.5 : 1.5}
                opacity={highFired ? 0.45 : 1}
                label={`買${s.nameB}：第${i + 1}級 → ${pct(m.tier, 1)}${exitNote}${highFired ? '（已觸發）' : ''}`}
              />
            </g>
          )
        })}

        {/* left end label */}
        <text x={0} y={11} fontSize={10} fill="var(--muted)">買{s.nameA}</text>
        <text x={0} y={BAR_H - 2} fontSize={10} fill="var(--muted)">{pct(lo, 1)}</text>

        {/* right end label */}
        <text x={BAR_W} y={11} fontSize={10} fill="var(--muted)" textAnchor="end">買{s.nameB}</text>
        <text x={BAR_W} y={BAR_H - 2} fontSize={10} fill="var(--muted)" textAnchor="end">{pct(hi, 1)}</text>

        {/* diff=0 tick -- always shown (even when flat), just without the
            "回流" label when there's no open position to flow back from */}
        <TickMark
          x={resetX} height={4} stroke="#f5a623" strokeWidth={2} opacity={isOpen ? 1 : 0.6}
          label={isOpen ? '回流 → 0.00%' : '中點 → 0.00%'}
        />
        {isOpen && <text x={resetX} y={BAR_H - 2} fontSize={9} fill="#f5a623" textAnchor="middle">回流</text>}

        {/* current position marker -- sits at curDiff itself now, not a
            fixed zero-move reference point */}
        <polygon
          points={`${curX - 4},${BAR_Y - 10} ${curX + 4},${BAR_Y - 10} ${curX},${BAR_Y - 4}`}
          fill={MARKER_COLOR}
        />
        <line x1={curX} x2={curX} y1={BAR_Y - 4} y2={BAR_Y + BAR_H_TRACK + 4} stroke={MARKER_COLOR} strokeWidth={2.5} />

        {/* live (intraday, tracked-pairs-only) position -- same diff units
            as everything else on this bar now, so it's just toX(liveDiff),
            no separate price-move conversion needed. */}
        {liveX != null && (
          <TickMark
            x={liveX} height={9} stroke="#ffd60a" strokeWidth={2.5} opacity={1}
            label={`即時diff → ${pct(liveDiff, 2)}`}
          />
        )}
      </svg>
      {!hideCaption && <ThresholdBarCaption s={s} liveDiff={liveDiff} />}
    </div>
  )
}

// Extracted so lite can reposition it (after its own PositionBar) instead
// of directly under the signal svg -- see ThresholdBar's hideCaption.
export function ThresholdBarCaption({ s, liveDiff }) {
  if (s.entry_high == null) return null
  const curDiff = s.outcome_known ? s.actual_diff : s.basis_diff
  const marks = s.tier_marks
    ? s.tier_marks.map((m) => ({ tier: m.tier, fired: m.fired }))
    : [{ tier: s.trigger, fired: s.is_open_before }]
  const firedCount = marks.filter((m) => m.fired).length
  return (
    <div style={{ fontSize: 11, color: 'var(--muted)' }}>
      目前 {pct(curDiff)} ｜ 基準：{s.basis_date}
      {s.engine === 'tiered' && ` ｜ 已觸發 ${firedCount}/${marks.length}級`}
      {s.engine === 'band' && ` ｜ 目前級別 ${firedCount}/${marks.length}`}
      {liveDiff != null && <span style={{ color: '#ffd60a' }}> ｜ 即時diff {pct(liveDiff, 2)}</span>}
    </div>
  )
}

// A tick on the threshold bar: a wide invisible line widens the hover
// hit-area (the visible tick itself is thin), and the tooltip is a plain
// CSS show/hide (via .tick-group:hover .tick-tip) instead of the native
// SVG <title> -- instant, no browser hover-delay.
function TickMark({ x, height, stroke, strokeWidth, opacity, label }) {
  const y1 = BAR_Y - height
  const y2 = BAR_Y + BAR_H_TRACK + height
  return (
    <g className="tick-group">
      <line x1={x} x2={x} y1={y1 - 6} y2={y2 + 6} stroke="transparent" strokeWidth={14} />
      <line x1={x} x2={x} y1={y1} y2={y2} stroke={stroke} strokeWidth={strokeWidth} opacity={opacity} />
      <foreignObject x={x - 70} y={y1 - 4} width={140} height={1} style={{ overflow: 'visible', pointerEvents: 'none' }}>
        <div className="tick-tip" style={{ position: 'relative' }}>
          <div className="tick-tip-inner" style={{ top: 'auto', bottom: 8 }}>{label}</div>
        </div>
      </foreignObject>
    </g>
  )
}
