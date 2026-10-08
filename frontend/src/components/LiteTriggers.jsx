// Shared by the 配對策略 page and the header's PiP mini window.

// after is always 1 or 2 here -- a move to level 0 is reset_today, handled
// separately by the caller (never routed through this function).
const LEVEL_WEIGHTS = { 1: '75/25', 2: '100/0' }

// A level-change event (entered_today) covers three genuinely different
// moves under this mechanism: escalating further out (0->1, 1->2), pulling
// back once (2->1, the only de-escalation the state machine allows), or
// flipping which side is strong (always via a same-day reset+re-entry --
// see pair_strategy_lite.py -- which can land back on the same level with
// the opposite side). before/after are both 0-2; before is only available
// where the caller tracked it (signal_for_target's historical branch, and
// live_check's baseline) -- undefined before that just reads as "moved to
// level N" with no direction implied.
export function levelChangeLabel(before, after) {
  const label = `T${after} (${LEVEL_WEIGHTS[after]})`
  if (before == null) return `切換至${label}`
  if (after > before) return `加碼至${label}`
  if (after < before) return `減碼至${label}`
  return `反轉方向，仍${label}`
}

export function TriggerList({ liveResults }) {
  const triggered = liveResults.filter((r) => r.entered_today || r.reset_today)
  if (triggered.length === 0) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>目前沒有</div>
  return triggered.map((r) => (
    <div key={r.key} className="up" style={{ fontSize: 13, marginBottom: 4 }}>
      {r.nameA}/{r.nameB} — {r.entered_today ? levelChangeLabel(r.tier_index_before, r.tier_index) : '回到50/50'}
    </div>
  ))
}
