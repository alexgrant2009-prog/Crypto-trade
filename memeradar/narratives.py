"""Narrative tracking: count how fast words and tickers spread, not how often they appear.

A term mentioned 5 times in the last hour after 0 mentions all day beats a term
mentioned 50 times every hour. Velocity finds narratives early. Volume finds them late.
"""
import re
import time

from .http import get_json

TICKER_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,19}")


def extract_terms(text, stopwords):
    text = text or ""
    tickers = {"$" + t.lower() for t in TICKER_RE.findall(text)}
    words = {w.lower() for w in WORD_RE.findall(text)}
    words = {w for w in words if w not in stopwords and not w.isdigit()}
    return tickers | words


def record(conn, source, source_id, text, ts, stopwords):
    terms = extract_terms(text, stopwords)
    conn.executemany(
        "INSERT OR IGNORE INTO mentions(source_id, source, term, ts) VALUES (?,?,?,?)",
        [(source_id, source, t, ts) for t in terms],
    )
    conn.commit()


def fetch_reddit(subreddit, user_agent):
    """Newest posts from a subreddit via public JSON. Reddit blocks this sometimes. The bot keeps running."""
    data = get_json(f"https://www.reddit.com/r/{subreddit}/new.json", user_agent, params={"limit": 100})
    posts = ((data or {}).get("data") or {}).get("children") or []
    out = []
    for p in posts:
        d = p.get("data") or {}
        out.append({
            "id": f"reddit:{d.get('id')}",
            "text": f"{d.get('title', '')} {d.get('selftext', '')[:500]}",
            "ts": float(d.get("created_utc") or time.time()),
        })
    return out


def heat(conn, term, cfg, now=None, exclude_id=""):
    """Ratio of recent mention rate to baseline rate. 1.0 means no change.

    exclude_id drops one source so a token's own description never inflates its own heat.
    """
    now = now or time.time()
    window = cfg.narrative_window_minutes * 60
    baseline = cfg.narrative_baseline_hours * 3600
    recent = conn.execute(
        "SELECT COUNT(*) FROM mentions WHERE term=? AND ts>=? AND source_id!=?",
        (term, now - window, exclude_id),
    ).fetchone()[0]
    older = conn.execute(
        "SELECT COUNT(*) FROM mentions WHERE term=? AND ts>=? AND ts<? AND source_id!=?",
        (term, now - window - baseline, now - window, exclude_id),
    ).fetchone()[0]
    baseline_per_window = older / (baseline / window)
    return recent, (recent + 1) / (baseline_per_window + 1)


def hot_terms(conn, cfg, min_recent=3, min_heat=3.0, limit=15, now=None):
    now = now or time.time()
    window = cfg.narrative_window_minutes * 60
    rows = conn.execute(
        "SELECT term FROM mentions WHERE ts>=? GROUP BY term HAVING COUNT(*)>=?",
        (now - window, min_recent),
    ).fetchall()
    scored = []
    for (term,) in rows:
        recent, h = heat(conn, term, cfg, now)
        if h >= min_heat:
            scored.append((term, recent, round(h, 2)))
    return sorted(scored, key=lambda x: x[2], reverse=True)[:limit]


def mark_started(conn, now=None):
    """Remember when this database first started collecting. Kept across restarts."""
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('started_at', ?)", (str(now or time.time()),))
    conn.commit()


def history_ready(conn, cfg, now=None):
    """Heat needs a full baseline. Before that, every repeated word looks hot."""
    now = now or time.time()
    row = conn.execute("SELECT value FROM meta WHERE key='started_at'").fetchone()
    if not row:
        return False
    needed = cfg.narrative_window_minutes * 60 + cfg.narrative_baseline_hours * 3600
    return now - float(row[0]) >= needed


def token_narrative_heat(conn, snap, description, cfg, now=None, exclude_id=""):
    """Best heat among the token's own name, symbol, and description terms.

    Returns (None, 1.0), meaning no narrative boost, until history_ready.
    """
    if not history_ready(conn, cfg, now):
        return None, 1.0
    text = f"{snap['name']} {snap['symbol']} ${snap['symbol']} {description or ''}"
    best_term, best = None, 1.0
    for term in extract_terms(text, cfg.stopwords):
        _, h = heat(conn, term, cfg, now, exclude_id)
        if h > best:
            best_term, best = term, h
    return best_term, best
