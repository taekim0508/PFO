"""The per-visitor limit counts the last minute and the last day, on an injected clock."""

from portfolio_bot.api.rate_limit import DAY, RateLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def limiter(per_minute=2, per_day=100):
    clock = Clock()
    return RateLimiter(per_minute=per_minute, per_day=per_day, clock=clock), clock


def test_allows_up_to_the_minute_limit_then_says_how_long_to_wait():
    limit, clock = limiter(per_minute=2)

    assert limit.check("a") is None
    clock.now += 10
    assert limit.check("a") is None
    clock.now += 5

    assert limit.check("a") == 45.0  # the first request leaves the window 60s after it


def test_a_refused_request_does_not_count():
    limit, clock = limiter(per_minute=1)
    limit.check("a")
    for _ in range(5):
        limit.check("a")

    clock.now += 60.5

    assert limit.check("a") is None


def test_visitors_are_counted_separately():
    limit, _ = limiter(per_minute=1)

    assert limit.check("a") is None
    assert limit.check("b") is None
    assert limit.check("a") is not None


def test_the_day_limit_holds_even_when_each_minute_is_quiet():
    limit, clock = limiter(per_minute=10, per_day=3)
    for _ in range(3):
        assert limit.check("a") is None
        clock.now += 120

    wait = limit.check("a")

    assert wait is not None and wait > 60
    clock.now += wait
    assert limit.check("a") is None


def test_idle_visitors_are_forgotten_after_a_day():
    limit, clock = limiter()
    limit.check("a")
    clock.now += DAY + 1

    limit.forget_idle()

    assert limit._hits == {}
