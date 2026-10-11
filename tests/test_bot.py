import time

import pytest

from memeradar import db, narratives, paper, safety, scoring
from memeradar.config import Config
from memeradar.main import run_cycle

NOW = 1_800_000_000.0
MINT = "GoodMint111"


def make_pair(mint=MINT, price="0.001", liq=50_000, vol_h1=60_000, buys_h1=400, sells_h1=150,
              buys_m5=30, age_h=2, change_h1=50, symbol="CATZ", name="Cat Zilla"):
    return {
        "url": f"https://dexscreener.com/solana/{mint}",
        "baseToken": {"address": mint, "symbol": symbol, "name": name},
        "priceUsd": price,
        "liquidity": {"usd": liq},
        "volume": {"h1": vol_h1, "m5": 5000},
        "txns": {"h1": {"buys": buys_h1, "sells": sells_h1}, "m5": {"buys": buys_m5, "sells": 5}},
        "priceChange": {"h1": change_h1},
        "marketCap": 900_000,
        "pairCreatedAt": (NOW - age_h * 3600) * 1000,
    }


SAFE_REPORT = {
    "mintAuthority": None, "freezeAuthority": None,
    "topHolders": [{"address": f"h{i}", "pct": 2.0, "insider": False} for i in range(10)],
    "markets": [{"lp": {"lpLockedPct": 100}}], "risks": [], "rugged": False,
}


class FakeSources:
    def __init__(self, pairs, report=SAFE_REPORT, posts=()):
        self._pairs, self._report, self._posts = pairs, report, list(posts)

    def profiles(self):
        return [{"chainId": "solana", "tokenAddress": p["baseToken"]["address"],
                 "description": "the cat that eats dogs"} for p in self._pairs]

    def pairs(self, mints):
        return [p for p in self._pairs if p["baseToken"]["address"] in mints]

    def reddit(self, sub):
        return self._posts if sub == "solana" else []

    def safety_report(self, mint):
        return self._report


@pytest.fixture
def conn():
    return db.connect(":memory:")


@pytest.fixture
def cfg():
    return Config(reddit_subreddits=("solana",))


def hot_posts(word, n=8):
    return [{"id": f"reddit:{i}", "text": f"everyone talking about {word} today", "ts": NOW - 60 * i} for i in range(n)]


def test_safety_rejects_mint_authority_and_whales(cfg):
    bad = dict(SAFE_REPORT, mintAuthority="Dev111",
               topHolders=[{"address": "whale", "pct": 60, "insider": True}])
    ok, reasons = safety.evaluate(bad, cfg)
    assert not ok
    joined = " ".join(reasons)
    assert "mint authority" in joined and "top 10" in joined and "insider" in joined


def test_safety_missing_report_fails(cfg):
    assert safety.evaluate(None, cfg)[0] is False


def test_safety_passes_clean_token(cfg):
    assert safety.evaluate(SAFE_REPORT, cfg) == (True, [])


def test_narrative_velocity_beats_volume(conn, cfg):
    # 'steady' gets 2 mentions every hour for 7 hours. 'zilla' appears only in the last hour.
    for h in range(7):
        for k in range(2):
            narratives.record(conn, "x", f"s{h}{k}", "steady", NOW - h * 3600 - 60 - k, cfg.stopwords)
    for k in range(5):
        narratives.record(conn, "x", f"z{k}", "zilla", NOW - 60 - k, cfg.stopwords)
    _, steady = narratives.heat(conn, "steady", cfg, NOW)
    _, zilla = narratives.heat(conn, "zilla", cfg, NOW)
    assert zilla > 3 > steady


def test_own_description_does_not_create_heat(conn, cfg):
    narratives.record(conn, "dexscreener", "dex:A", "zilla", NOW, cfg.stopwords)
    snap = {"name": "Zilla", "symbol": "ZIL"}
    term, h = narratives.token_narrative_heat(conn, snap, "zilla", cfg, NOW, "dex:A")
    assert term is None and h == 1.0


def test_market_filters_reject_low_liquidity(cfg):
    from memeradar.dexscreener import snapshot
    ok, why = scoring.passes_market_filters(snapshot(make_pair(liq=2_000), NOW), cfg)
    assert not ok and "liquidity" in why[0]


def test_full_cycle_opens_paper_trade_on_hot_narrative(conn, cfg, capsys):
    run_cycle(conn, cfg, FakeSources([make_pair()], posts=hot_posts("zilla")), now=NOW)
    out = capsys.readouterr().out
    assert "[SIGNAL] CATZ" in out and "Paper buy" in out
    assert len(paper.open_positions(conn)) == 1


def test_unsafe_token_never_traded(conn, cfg):
    bad = dict(SAFE_REPORT, freezeAuthority="Dev111")
    run_cycle(conn, cfg, FakeSources([make_pair()], report=bad, posts=hot_posts("zilla")), now=NOW)
    assert paper.open_positions(conn) == []


def test_take_profit_and_rug_exits(conn, cfg):
    from memeradar.dexscreener import snapshot
    run_cycle(conn, cfg, FakeSources([make_pair()], posts=hot_posts("zilla")), now=NOW)
    # Price triples: take profit should fire after fees and slippage.
    closed = paper.update_positions(conn, {MINT: snapshot(make_pair(price="0.003"), NOW)}, cfg, NOW + 600)
    assert closed[0][1] == "take profit" and closed[0][2] > 100

    conn2 = db.connect(":memory:")
    run_cycle(conn2, cfg, FakeSources([make_pair()], posts=hot_posts("zilla")), now=NOW)
    closed = paper.update_positions(conn2, {MINT: snapshot(make_pair(liq=1_000), NOW)}, cfg, NOW + 600)
    assert closed[0][1] == "rug" and paper.stats(conn2, cfg)["realized_pnl_usd"] == -20.0


def test_round_trip_at_flat_price_loses_costs(conn, cfg):
    from memeradar.dexscreener import snapshot
    run_cycle(conn, cfg, FakeSources([make_pair()], posts=hot_posts("zilla")), now=NOW)
    closed = paper.update_positions(conn, {MINT: snapshot(make_pair(), NOW)}, cfg, NOW + 25 * 3600)
    assert closed[0][1] == "max hold time"
    # 3% slippage + 1% fee each way: about -7.8% on a flat price. Costs are real.
    assert -9 < closed[0][2] < -7


def test_same_token_alerted_once(conn, cfg, capsys):
    src = FakeSources([make_pair()], posts=hot_posts("zilla"))
    run_cycle(conn, cfg, src, now=NOW)
    run_cycle(conn, cfg, src, now=NOW + 60)
    assert capsys.readouterr().out.count("[SIGNAL]") == 1
