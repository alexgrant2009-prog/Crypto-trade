"""DexScreener public API (free, no key). Docs: https://docs.dexscreener.com/api/reference"""
import time

from .http import get_json

BASE = "https://api.dexscreener.com"
CHAIN = "solana"


def latest_profiles(user_agent):
    """Tokens that recently published a DexScreener profile. Returns list of dicts."""
    data = get_json(f"{BASE}/token-profiles/latest/v1", user_agent) or []
    return [p for p in data if p.get("chainId") == CHAIN]


def latest_boosts(user_agent):
    """Tokens whose teams recently paid for boosts. Paid promotion, so treat as a weak signal."""
    data = get_json(f"{BASE}/token-boosts/latest/v1", user_agent) or []
    return [p for p in data if p.get("chainId") == CHAIN]


def pairs_for_tokens(mints, user_agent):
    """Fetch trading pairs for up to many mints (API takes 30 per call)."""
    pairs = []
    mints = list(dict.fromkeys(mints))
    for i in range(0, len(mints), 30):
        chunk = ",".join(mints[i:i + 30])
        data = get_json(f"{BASE}/tokens/v1/{CHAIN}/{chunk}", user_agent)
        if isinstance(data, list):
            pairs.extend(data)
    return pairs


def best_pair_by_token(pairs):
    """Keep the most liquid pair for each token mint."""
    best = {}
    for p in pairs:
        mint = (p.get("baseToken") or {}).get("address")
        if not mint:
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if mint not in best or liq > ((best[mint].get("liquidity") or {}).get("usd") or 0):
            best[mint] = p
    return best


def snapshot(pair, now=None):
    """Flatten a DexScreener pair into the numbers the bot uses."""
    now = now or time.time()
    txns_h1 = (pair.get("txns") or {}).get("h1") or {}
    txns_m5 = (pair.get("txns") or {}).get("m5") or {}
    created_ms = pair.get("pairCreatedAt")
    base = pair.get("baseToken") or {}
    return {
        "mint": base.get("address"),
        "symbol": base.get("symbol") or "?",
        "name": base.get("name") or "",
        "url": pair.get("url"),
        "price_usd": float(pair.get("priceUsd") or 0),
        "liquidity_usd": float((pair.get("liquidity") or {}).get("usd") or 0),
        "volume_h1": float((pair.get("volume") or {}).get("h1") or 0),
        "volume_m5": float((pair.get("volume") or {}).get("m5") or 0),
        "buys_h1": int(txns_h1.get("buys") or 0),
        "sells_h1": int(txns_h1.get("sells") or 0),
        "buys_m5": int(txns_m5.get("buys") or 0),
        "sells_m5": int(txns_m5.get("sells") or 0),
        "price_change_h1": float((pair.get("priceChange") or {}).get("h1") or 0),
        "market_cap": float(pair.get("marketCap") or pair.get("fdv") or 0),
        "age_hours": (now - created_ms / 1000) / 3600 if created_ms else None,
    }
