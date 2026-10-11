"""Small HTTP helper with timeouts and polite retries on rate limits."""
import time

import requests


def get_json(url, user_agent, params=None, retries=3, timeout=15):
    """Return parsed JSON, or None after repeated failures. Never raises on network errors."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": user_agent, "Accept": "application/json"})
            if resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code >= 400:
                return None
            return resp.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 ** attempt)
    return None
