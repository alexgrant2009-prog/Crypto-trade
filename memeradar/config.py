"""All tunable settings in one place. Change numbers here, not in the code."""
from dataclasses import dataclass, field


@dataclass
class Config:
    # How often the main loop runs, in seconds.
    poll_seconds: int = 60

    # Basic market filters. Tokens failing these never reach the safety check.
    min_liquidity_usd: float = 10_000
    min_volume_h1_usd: float = 5_000
    max_age_hours: float = 24
    min_buy_sell_ratio_h1: float = 1.1

    # Safety filters (on-chain data from RugCheck).
    max_top10_holder_pct: float = 30.0
    min_lp_locked_pct: float = 80.0
    reject_risk_levels: tuple = ("danger",)

    # Score needed (0 to 100) before the bot opens a paper trade.
    min_entry_score: float = 60.0

    # Paper trading. Fees and slippage are deliberately pessimistic.
    starting_balance_usd: float = 200.0
    position_size_usd: float = 20.0
    max_open_positions: int = 5
    fee_pct_per_side: float = 1.0
    slippage_pct_per_side: float = 3.0
    take_profit_pct: float = 100.0
    stop_loss_pct: float = -30.0
    max_hold_hours: float = 24.0
    # If pool liquidity falls below this share of entry liquidity, treat as a rug (total loss).
    rug_liquidity_drop_ratio: float = 0.2

    # Narrative tracking.
    reddit_subreddits: tuple = ("solana", "CryptoMoonShots", "memecoins")
    narrative_window_minutes: int = 60
    narrative_baseline_hours: int = 6

    db_path: str = "memeradar.db"
    user_agent: str = "memeradar/0.1 (personal research bot)"
    stopwords: frozenset = field(default_factory=lambda: frozenset(
        "the and for you this that with are was from have will your just our out not but all "
        "its it's get new now can has one who what when how coin token sol solana crypto meme "
        "memecoin pump fun launch launched community first best more about into they their".split()
    ))
