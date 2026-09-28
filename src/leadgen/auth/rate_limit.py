"""In-memory sliding-window rate limits for login, reset and setup.

Per-process only. This complements the persistent per-account lockout held in
the ``users`` table; a multi-instance deployment would need a shared store.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from leadgen.auth.errors import RateLimited

LOGIN_IP_LIMIT = (20, 15 * 60)
LOGIN_USERNAME_LIMIT = (10, 15 * 60)
RESET_IP_LIMIT = (10, 15 * 60)
SETUP_IP_LIMIT = (5, 15 * 60)


class SlidingWindowLimiter:
    """Counts hits per key and rejects once the window holds ``limit`` of them."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, now: Optional[float] = None) -> None:
        """Record an attempt for ``key``, raising ``RateLimited`` when exhausted."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            cutoff = moment - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = int(self.window_seconds - (moment - hits[0])) + 1
                raise RateLimited(f"Too many attempts. Try again in {retry_after} seconds.")
            hits.append(moment)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_login_ip = SlidingWindowLimiter(*LOGIN_IP_LIMIT)
_login_username = SlidingWindowLimiter(*LOGIN_USERNAME_LIMIT)
_reset_ip = SlidingWindowLimiter(*RESET_IP_LIMIT)
_setup_ip = SlidingWindowLimiter(*SETUP_IP_LIMIT)


def check_login_attempt(ip_address: Optional[str]) -> None:
    """Count every login attempt per client address."""
    if ip_address:
        _login_ip.check(ip_address)


def check_login_failure(username_normalized: str) -> None:
    """Count failed logins per username, in addition to the account lockout."""
    if username_normalized:
        _login_username.check(username_normalized)


def check_reset_attempt(ip_address: Optional[str]) -> None:
    if ip_address:
        _reset_ip.check(ip_address)


def check_setup_attempt(ip_address: Optional[str]) -> None:
    if ip_address:
        _setup_ip.check(ip_address)


def reset_limits() -> None:
    """Drop all recorded attempts (used by the test suite)."""
    for limiter in (_login_ip, _login_username, _reset_ip, _setup_ip):
        limiter.clear()
