"""Read-only view of the Sinopac stock account's inventory, for the 庫存 tab.

Display only -- deliberately NOT wired into the pair strategy's position
state (lite_position_override): the real portfolio has holdings that live
at other brokers/accounts, so this account alone isn't "the" position.
"""
import db
import sinopac_quote


def _resolve_symbol(code):
    """Sinopac reports a bare code ('2327'); the app keys everything by
    Yahoo symbol ('2327.TW' / '5483.TWO'). Returns (symbol_or_None, name)."""
    for suffix in (".TW", ".TWO"):
        info = db.get_symbol(code + suffix)
        if info:
            return info["symbol"], info["name"]
    return None, code


def build_holdings():
    raw = sinopac_quote.get_positions(unit="Share")

    positions = []
    for r in raw:
        qty = r.get("quantity") or 0
        if qty == 0:
            continue
        symbol, name = _resolve_symbol(r["code"])
        avg_cost, last = r.get("price"), r.get("last_price")
        cost = round(qty * avg_cost, 2) if avg_cost is not None else None
        value = round(qty * last, 2) if last is not None else None
        pnl = r.get("pnl")
        quote = db.latest_quote(symbol) if symbol else None
        positions.append({
            "code": r["code"],
            "symbol": symbol,
            "name": name,
            "quantity": qty,
            "avg_cost": avg_cost,
            "last_price": last,
            "cost": cost,
            "market_value": value,
            # Sinopac's own figure -- it's net of estimated fees/tax, so it
            # won't equal market_value - cost.
            "pnl": pnl,
            "pnl_pct": round(pnl / cost * 100, 2) if (pnl is not None and cost) else None,
            "day_change_pct": quote["change_pct"] if quote else None,
        })
    positions.sort(key=lambda p: p["market_value"] or 0, reverse=True)

    total_cost = sum(p["cost"] or 0 for p in positions)
    total_value = sum(p["market_value"] or 0 for p in positions)
    total_pnl = sum(p["pnl"] or 0 for p in positions)
    return {
        "positions": positions,
        "totals": {
            "cost": round(total_cost, 2),
            "market_value": round(total_value, 2),
            "pnl": round(total_pnl, 2),
            "pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else None,
        },
    }
