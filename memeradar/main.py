"""Main loop: scan, screen, score, alert, paper trade. Run with: python -m memeradar run"""
import argparse
import csv
import json
import time

from . import alerts, db, dexscreener, narratives, paper, safety, scoring
from .config import Config


class LiveSources:
    """Real network data. Tests swap this for fake data."""

    def __init__(self, cfg):
        self.ua = cfg.user_agent

    def profiles(self):
        return dexscreener.latest_profiles(self.ua) + dexscreener.latest_boosts(self.ua)

    def pairs(self, mints):
        return dexscreener.pairs_for_tokens(mints, self.ua)

    def reddit(self, sub):
        return narratives.fetch_reddit(sub, self.ua)

    def safety_report(self, mint):
        return safety.fetch_report(mint, self.ua)


def run_cycle(conn, cfg, src, now=None, verbose=False):
    now = now or time.time()
    narratives.mark_started(conn, now)

    # 1. Collect narrative text from free sources.
    for sub in cfg.reddit_subreddits:
        for post in src.reddit(sub):
            narratives.record(conn, "reddit", post["id"], post["text"], post["ts"], cfg.stopwords)

    profiles = src.profiles()
    if not profiles:
        print("[warn] DexScreener returned no tokens. Check your internet connection.", flush=True)
    descriptions = {}
    for p in profiles:
        mint = p.get("tokenAddress")
        if not mint:
            continue
        descriptions[mint] = p.get("description") or ""
        narratives.record(conn, "dexscreener", f"dex:{mint}", descriptions[mint], now, cfg.stopwords)

    # 2. Price data for new candidates plus anything we hold.
    held = [r["mint"] for r in paper.open_positions(conn)]
    pairs = src.pairs(list(descriptions) + held)
    snaps = {m: dexscreener.snapshot(p, now) for m, p in dexscreener.best_pair_by_token(pairs).items()}

    # 3. Manage open paper trades first.
    for pos, reason, pnl in paper.update_positions(conn, snaps, cfg, now):
        alerts.send(f"[PAPER EXIT] {pos['symbol']} {reason} | PnL {pnl:+.1f}%")

    # 4. Screen new candidates.
    for mint in descriptions:
        snap = snaps.get(mint)
        if not snap or conn.execute("SELECT 1 FROM alerts WHERE mint=?", (mint,)).fetchone():
            continue
        ok, why = scoring.passes_market_filters(snap, cfg)
        if not ok:
            if verbose:
                print(f"skip {snap['symbol']}: {'; '.join(why)}")
            continue

        term, heat = narratives.token_narrative_heat(conn, snap, descriptions[mint], cfg, now, f"dex:{mint}")
        sc = scoring.score(snap, heat, cfg)
        if sc < cfg.min_entry_score:
            if verbose:
                print(f"skip {snap['symbol']}: score {sc}")
            continue

        # Safety check last, because RugCheck calls are the slowest.
        safe, risks = safety.evaluate(src.safety_report(mint), cfg)
        conn.execute("INSERT OR REPLACE INTO alerts(mint, ts, score, passed_safety, reasons) VALUES (?,?,?,?,?)",
                     (mint, now, sc, int(safe), json.dumps(risks)))
        conn.commit()
        if not safe:
            if verbose:
                print(f"REJECT {snap['symbol']} (score {sc}): {'; '.join(risks)}")
            continue

        # Save every input behind the decision, so later you learn which ones predict winners.
        info = {k: snap[k] for k in ("liquidity_usd", "volume_h1", "volume_m5", "buys_h1", "sells_h1",
                                     "buys_m5", "sells_m5", "price_change_h1", "market_cap", "age_hours")}
        info.update(narrative_term=term, narrative_heat=round(heat, 2))
        skipped = paper.try_open(conn, snap, sc, cfg, now, info)
        narrative = f"hot term '{term}' x{heat:.1f}" if term else "no hot narrative"
        alerts.send(
            f"[SIGNAL] {snap['symbol']} score {sc} | mcap ${snap['market_cap']:,.0f} | "
            f"liq ${snap['liquidity_usd']:,.0f} | age {snap['age_hours']:.1f}h | {narrative}\n"
            f"{snap['url']}\n"
            + (f"Paper buy ${cfg.position_size_usd:.0f}" if skipped is None else f"No paper buy: {skipped}")
        )


def print_report(conn, cfg):
    print(json.dumps(paper.stats(conn, cfg), indent=2))
    print("\nHot narratives right now (term, mentions last hour, heat):")
    for t in narratives.hot_terms(conn, cfg):
        print(f"  {t[0]:<20} {t[1]:>4}  x{t[2]}")
    print("\nLast 10 closed trades:")
    for r in conn.execute("SELECT * FROM positions WHERE closed_at IS NOT NULL ORDER BY closed_at DESC LIMIT 10"):
        pnl = (r["proceeds_usd"] / r["size_usd"] - 1) * 100
        print(f"  {r['symbol']:<10} {pnl:+7.1f}%  {r['exit_reason']}")


EXPORT_FIELDS = ["symbol", "mint", "score", "opened_at", "closed_at", "hold_minutes", "pnl_pct", "exit_reason",
                 "liquidity_usd", "volume_h1", "volume_m5", "buys_h1", "sells_h1", "buys_m5", "sells_m5",
                 "price_change_h1", "market_cap", "age_hours", "narrative_term", "narrative_heat", "url"]


def export_trades(conn, path="trades.csv"):
    """Write every closed trade with its entry inputs to a CSV file you open in Excel."""
    rows = conn.execute("SELECT * FROM positions WHERE closed_at IS NOT NULL ORDER BY opened_at").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            info = json.loads(r["entry_info"] or "{}")
            w.writerow({
                **info,
                "symbol": r["symbol"], "mint": r["mint"], "score": r["score"], "url": r["url"],
                "opened_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["opened_at"])),
                "closed_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["closed_at"])),
                "hold_minutes": round((r["closed_at"] - r["opened_at"]) / 60, 1),
                "pnl_pct": round((r["proceeds_usd"] / r["size_usd"] - 1) * 100, 1),
                "exit_reason": r["exit_reason"],
            })
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Solana meme coin radar with paper trading")
    parser.add_argument("command", choices=["run", "once", "report", "export"])
    parser.add_argument("-v", "--verbose", action="store_true", help="print why tokens get skipped")
    args = parser.parse_args()

    cfg = Config()
    conn = db.connect(cfg.db_path)
    if args.command == "report":
        print_report(conn, cfg)
        if not narratives.history_ready(conn, cfg):
            print(f"\nNarrative scoring warms up for the first {cfg.narrative_baseline_hours + 1} hours. "
                  "No narrative boost until then.")
        return
    if args.command == "export":
        n = export_trades(conn)
        print(f"Wrote {n} closed trades to trades.csv")
        return

    src = LiveSources(cfg)
    print(f"Meme Radar started. Paper balance ${paper.cash(conn, cfg):.2f}. Ctrl+C to stop.")
    while True:
        try:
            run_cycle(conn, cfg, src, verbose=args.verbose)
        except Exception as exc:  # keep the bot alive through bad data
            print(f"[cycle error] {exc!r}", flush=True)
        if args.command == "once":
            break
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
