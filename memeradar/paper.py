"""Paper trading: simulated buys and sells with pessimistic fees and slippage.

Paper results still flatter you. Real snipes fill worse than a 60 second poll suggests,
and you can't always sell into a crash. Treat a paper profit as a minimum bar, not proof.
"""
import time


def _net_value(tokens, price, cfg):
    gross = tokens * price * (1 - cfg.slippage_pct_per_side / 100)
    return gross * (1 - cfg.fee_pct_per_side / 100)


def cash(conn, cfg):
    spent = conn.execute("SELECT COALESCE(SUM(size_usd),0) FROM positions").fetchone()[0]
    back = conn.execute("SELECT COALESCE(SUM(proceeds_usd),0) FROM positions WHERE closed_at IS NOT NULL").fetchone()[0]
    return cfg.starting_balance_usd - spent + back


def open_positions(conn):
    return conn.execute("SELECT * FROM positions WHERE closed_at IS NULL").fetchall()


def has_traded(conn, mint):
    return conn.execute("SELECT 1 FROM positions WHERE mint=?", (mint,)).fetchone() is not None


def try_open(conn, snap, score, cfg, now=None):
    """Open a position if rules allow. Returns a reason string if skipped, else None."""
    now = now or time.time()
    if has_traded(conn, snap["mint"]):
        return "already traded this token"
    if len(open_positions(conn)) >= cfg.max_open_positions:
        return "max open positions reached"
    if cash(conn, cfg) < cfg.position_size_usd:
        return "not enough paper cash"
    size = cfg.position_size_usd
    entry = snap["price_usd"] * (1 + cfg.slippage_pct_per_side / 100)
    tokens = size * (1 - cfg.fee_pct_per_side / 100) / entry
    conn.execute(
        "INSERT INTO positions(mint, symbol, url, score, opened_at, entry_price, entry_liquidity, size_usd, tokens)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (snap["mint"], snap["symbol"], snap["url"], score, now, entry, snap["liquidity_usd"], size, tokens),
    )
    conn.commit()
    return None


def _close(conn, pos, price, proceeds, reason, now):
    conn.execute(
        "UPDATE positions SET closed_at=?, exit_price=?, proceeds_usd=?, exit_reason=? WHERE id=?",
        (now, price, proceeds, reason, pos["id"]),
    )
    conn.commit()


def update_positions(conn, snaps_by_mint, cfg, now=None):
    """Check every open position against exit rules. Returns list of (position, reason, pnl_pct)."""
    now = now or time.time()
    closed = []
    for pos in open_positions(conn):
        snap = snaps_by_mint.get(pos["mint"])
        held_hours = (now - pos["opened_at"]) / 3600

        if snap is None:
            if held_hours >= cfg.max_hold_hours:
                _close(conn, pos, 0.0, 0.0, "no market data at timeout, assumed dead", now)
                closed.append((pos, "dead", -100.0))
            continue

        if snap["liquidity_usd"] < pos["entry_liquidity"] * cfg.rug_liquidity_drop_ratio:
            _close(conn, pos, snap["price_usd"], 0.0, "liquidity pulled, assumed rug", now)
            closed.append((pos, "rug", -100.0))
            continue

        value = _net_value(pos["tokens"], snap["price_usd"], cfg)
        pnl_pct = (value / pos["size_usd"] - 1) * 100
        reason = None
        if pnl_pct >= cfg.take_profit_pct:
            reason = "take profit"
        elif pnl_pct <= cfg.stop_loss_pct:
            reason = "stop loss"
        elif held_hours >= cfg.max_hold_hours:
            reason = "max hold time"
        if reason:
            _close(conn, pos, snap["price_usd"], value, reason, now)
            closed.append((pos, reason, round(pnl_pct, 1)))
    return closed


def stats(conn, cfg):
    rows = conn.execute("SELECT * FROM positions WHERE closed_at IS NOT NULL").fetchall()
    n = len(rows)
    wins = [r for r in rows if r["proceeds_usd"] > r["size_usd"]]
    pnl = sum(r["proceeds_usd"] - r["size_usd"] for r in rows)
    return {
        "closed_trades": n,
        "open_trades": len(open_positions(conn)),
        "win_rate_pct": round(100 * len(wins) / n, 1) if n else 0.0,
        "realized_pnl_usd": round(pnl, 2),
        "avg_pnl_per_trade_usd": round(pnl / n, 2) if n else 0.0,
        "cash_usd": round(cash(conn, cfg), 2),
        "rugs": sum(1 for r in rows if "rug" in (r["exit_reason"] or "") or "dead" in (r["exit_reason"] or "")),
    }
