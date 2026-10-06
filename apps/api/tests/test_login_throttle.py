from app.auth.throttle import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_and_reports_seconds_until_the_oldest_failure_expires():
    clock = Clock()
    throttle = LoginThrottle(limit=5, window_seconds=900, clock=clock)
    for _ in range(4):
        throttle.record_failure("1.1.1.1")
        clock.now += 10
    assert throttle.retry_after("1.1.1.1") is None

    throttle.record_failure("1.1.1.1")

    assert throttle.retry_after("1.1.1.1") == 860


def test_failures_older_than_the_window_are_forgotten():
    clock = Clock()
    throttle = LoginThrottle(limit=5, window_seconds=900, clock=clock)
    for _ in range(5):
        throttle.record_failure("1.1.1.1")

    clock.now += 900

    assert throttle.retry_after("1.1.1.1") is None


def test_addresses_are_counted_separately_and_reset_clears_one_address():
    throttle = LoginThrottle(limit=2, window_seconds=900, clock=Clock())
    throttle.record_failure("1.1.1.1")
    throttle.record_failure("1.1.1.1")

    assert throttle.retry_after("2.2.2.2") is None
    assert throttle.retry_after("1.1.1.1") is not None

    throttle.reset("1.1.1.1")

    assert throttle.retry_after("1.1.1.1") is None
