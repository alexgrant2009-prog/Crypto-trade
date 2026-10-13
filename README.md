# Meme Radar

A Solana meme coin scanner. Finds new tokens, rejects obvious rugs, tracks which
narratives spread fastest, and paper trades the survivors so you measure your edge
before you risk real money.

No real trades. No wallet. No private keys. Free data only.

## What it does every 60 seconds

1. Pulls new Solana token profiles and boosts from DexScreener.
2. Pulls new posts from r/solana, r/CryptoMoonShots, r/memecoins.
3. Measures narrative heat: how fast a word or $TICKER spreads in the last hour
   compared with the previous 6 hours.
4. Filters tokens by liquidity, volume, age, and buy/sell pressure.
5. Scores survivors 0 to 100 (momentum 40, freshness 15, activity 15, narrative 30).
6. Runs a RugCheck safety check: mint authority, freeze authority, holder
   concentration, insiders, locked liquidity.
7. Opens a $20 paper trade (from a $1,000 paper balance) on tokens scoring 60+ that pass every safety check.
8. Closes paper trades at +100% profit, -30% loss, 24 hours, or liquidity pulled.

## Setup (one time)

You need Python 3.10 or newer. Check with `python3 --version`.

```
git clone <this repo>
cd Crypto-trade
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```
python -m memeradar run          # runs forever, Ctrl+C to stop
python -m memeradar run -v       # also prints why each token got skipped
python -m memeradar report       # paper trading results and hot narratives
python -m memeradar export       # writes every closed trade and its inputs to trades.csv
python -m pytest                 # run the tests
```

Leave `run` going for days. Check `report` once a day.

## Optional: alerts on your phone (Telegram, free)

1. In Telegram, message @BotFather, send `/newbot`, copy the token.
2. Message your new bot once, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy your chat id.
3. Before running:
   ```
   export TELEGRAM_BOT_TOKEN=your_token
   export TELEGRAM_CHAT_ID=your_chat_id
   ```

## Tuning

Every threshold lives in `memeradar/config.py`. Change one number at a time and
compare `report` results over a week.

## How to judge the results

Run for 3 to 4 weeks and collect at least 50 closed trades. Then ask:

- Is `realized_pnl_usd` positive after fees and slippage?
- Does profit come from many trades or one lucky winner? Remove the best trade. Still positive?
- What share of exits are rugs?

If the answer to the first two is no, do not move to live trading. Adjust filters or stop.

## Known limits

- Narrative scoring stays off for the first 7 hours of a fresh database. Without a
  baseline, every repeated word looks hot.

- Paper fills beat real fills. Real snipers buy in the first seconds. This bot sees prices
  up to 60 seconds late and assumes you always get out. Treat paper profit as the
  minimum bar, not proof.
- No X (Twitter) data. The official API costs about $200/month. Reddit and DexScreener
  descriptions stand in for now. `narratives.py` takes any text source, so X or
  Telegram plug in later.
- Reddit sometimes blocks anonymous requests. The bot keeps running without it.
- RugCheck flags known tricks, not every scam. Passing the check is not safety.
