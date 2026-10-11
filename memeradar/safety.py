"""On-chain safety checks via the free RugCheck API (https://api.rugcheck.xyz/swagger)."""
import time

from .http import get_json

BASE = "https://api.rugcheck.xyz/v1"
_cache = {}
CACHE_SECONDS = 600


def fetch_report(mint, user_agent):
    hit = _cache.get(mint)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    report = get_json(f"{BASE}/tokens/{mint}/report", user_agent)
    _cache[mint] = (time.time(), report)
    return report


def evaluate(report, cfg):
    """Return (passed, reasons). Missing data counts as a fail. Unknown is unsafe."""
    if not report:
        return False, ["no safety report available"]
    reasons = []

    if report.get("mintAuthority"):
        reasons.append("mint authority active (dev can print more tokens)")
    if report.get("freezeAuthority"):
        reasons.append("freeze authority active (dev can freeze your tokens)")

    holders = report.get("topHolders") or []
    # Exclude pool/AMM accounts if RugCheck tags them as known accounts.
    known = report.get("knownAccounts") or {}
    real = [h for h in holders if h.get("owner") not in known and h.get("address") not in known]
    top10 = sum(float(h.get("pct") or 0) for h in real[:10])
    if top10 > cfg.max_top10_holder_pct:
        reasons.append(f"top 10 holders own {top10:.1f}% (max {cfg.max_top10_holder_pct}%)")
    insiders = [h for h in real if h.get("insider")]
    if insiders:
        reasons.append(f"{len(insiders)} insider wallets among top holders")

    lp_pcts = [float((m.get("lp") or {}).get("lpLockedPct") or 0) for m in report.get("markets") or []]
    lp_locked = max(lp_pcts) if lp_pcts else 0.0
    if lp_locked < cfg.min_lp_locked_pct:
        reasons.append(f"only {lp_locked:.0f}% of liquidity locked or burned")

    for r in report.get("risks") or []:
        if (r.get("level") or "").lower() in cfg.reject_risk_levels:
            reasons.append(f"RugCheck risk: {r.get('name')}")

    if report.get("rugged"):
        reasons.append("RugCheck marks this token as rugged")

    return not reasons, reasons
