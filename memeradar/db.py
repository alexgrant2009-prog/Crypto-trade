"""SQLite storage. One file, no server needed."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS mentions (
    source_id TEXT NOT NULL,
    source TEXT NOT NULL,
    term TEXT NOT NULL,
    ts REAL NOT NULL,
    UNIQUE(source_id, term)
);
CREATE INDEX IF NOT EXISTS idx_mentions_term_ts ON mentions(term, ts);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    symbol TEXT,
    url TEXT,
    score REAL,
    opened_at REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_liquidity REAL NOT NULL,
    size_usd REAL NOT NULL,
    tokens REAL NOT NULL,
    closed_at REAL,
    exit_price REAL,
    proceeds_usd REAL,
    exit_reason TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    mint TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    score REAL,
    passed_safety INTEGER,
    reasons TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
