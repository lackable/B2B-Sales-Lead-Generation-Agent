"""The in-memory sliding-window limiter and its module-level wrappers."""

import pytest

from leadgen.auth import rate_limit
from leadgen.auth.errors import RateLimited


def test_limiter_allows_up_to_the_limit_then_rejects():
    limiter = rate_limit.SlidingWindowLimiter(limit=3, window_seconds=60)

    for _ in range(3):
        limiter.check("client", now=10.0)

    with pytest.raises(RateLimited) as exc:
        limiter.check("client", now=11.0)
    assert "Try again in" in str(exc.value)


def test_limiter_tracks_keys_independently():
    limiter = rate_limit.SlidingWindowLimiter(limit=1, window_seconds=60)

    limiter.check("first", now=0.0)
    limiter.check("second", now=0.0)

    with pytest.raises(RateLimited):
        limiter.check("first", now=0.0)


def test_hits_age_out_of_the_window():
    limiter = rate_limit.SlidingWindowLimiter(limit=2, window_seconds=10)

    limiter.check("client", now=0.0)
    limiter.check("client", now=1.0)
    limiter.check("client", now=11.0)


def test_clear_drops_every_hit():
    limiter = rate_limit.SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("client", now=0.0)

    limiter.clear()

    limiter.check("client", now=0.0)


def test_wrappers_ignore_missing_keys_and_share_the_window(api_state_reset):
    rate_limit.check_login_attempt(None)
    rate_limit.check_login_failure("")
    rate_limit.check_reset_attempt(None)
    rate_limit.check_setup_attempt(None)

    for _ in range(rate_limit.LOGIN_IP_LIMIT[0]):
        rate_limit.check_login_attempt("10.0.0.1")

    with pytest.raises(RateLimited):
        rate_limit.check_login_attempt("10.0.0.1")

    for _ in range(rate_limit.LOGIN_USERNAME_LIMIT[0]):
        rate_limit.check_login_failure("alice")

    with pytest.raises(RateLimited):
        rate_limit.check_login_failure("alice")


def test_setup_and_reset_wrappers_enforce_their_own_limits(api_state_reset):
    for _ in range(rate_limit.SETUP_IP_LIMIT[0]):
        rate_limit.check_setup_attempt("10.0.0.2")
    with pytest.raises(RateLimited):
        rate_limit.check_setup_attempt("10.0.0.2")

    for _ in range(rate_limit.RESET_IP_LIMIT[0]):
        rate_limit.check_reset_attempt("10.0.0.3")
    with pytest.raises(RateLimited):
        rate_limit.check_reset_attempt("10.0.0.3")


def test_reset_limits_clears_every_limiter(api_state_reset):
    for _ in range(rate_limit.LOGIN_IP_LIMIT[0]):
        rate_limit.check_login_attempt("10.0.0.4")

    rate_limit.reset_limits()

    # The window is empty again, so the full quota is available.
    for _ in range(rate_limit.LOGIN_IP_LIMIT[0]):
        rate_limit.check_login_attempt("10.0.0.4")
