"""Turn market data and narrative heat into one 0 to 100 score."""


def passes_market_filters(s, cfg):
    reasons = []
    if s["liquidity_usd"] < cfg.min_liquidity_usd:
        reasons.append(f"liquidity ${s['liquidity_usd']:,.0f} below ${cfg.min_liquidity_usd:,.0f}")
    if s["volume_h1"] < cfg.min_volume_h1_usd:
        reasons.append(f"1h volume ${s['volume_h1']:,.0f} below ${cfg.min_volume_h1_usd:,.0f}")
    if s["age_hours"] is None or s["age_hours"] > cfg.max_age_hours:
        reasons.append("too old or unknown age")
    ratio = s["buys_h1"] / max(s["sells_h1"], 1)
    if ratio < cfg.min_buy_sell_ratio_h1:
        reasons.append(f"buy/sell ratio {ratio:.2f} below {cfg.min_buy_sell_ratio_h1}")
    if s["price_usd"] <= 0:
        reasons.append("no price")
    return not reasons, reasons


def score(s, narrative_heat, cfg):
    """Weights: momentum 40, freshness 15, early activity 15, narrative 30."""
    ratio = s["buys_h1"] / max(s["sells_h1"], 1)
    momentum = min(ratio / 3.0, 1.0) * 20
    turnover = s["volume_h1"] / max(s["liquidity_usd"], 1)
    momentum += min(turnover / 2.0, 1.0) * 20

    age = s["age_hours"] if s["age_hours"] is not None else cfg.max_age_hours
    freshness = 15 if age <= 6 else max(0.0, 15 * (cfg.max_age_hours - age) / (cfg.max_age_hours - 6))

    activity = min(s["buys_m5"] / 10.0, 1.0) * 15

    narrative = min(max(narrative_heat - 1.0, 0.0) / 4.0, 1.0) * 30

    # Punish tokens already up hugely in the last hour. You'd be buying the top.
    chase_penalty = 15 if s["price_change_h1"] > 300 else 0

    return round(max(0.0, momentum + freshness + activity + narrative - chase_penalty), 1)
