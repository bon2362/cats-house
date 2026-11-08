import urllib.error

from drive_backup.health import ping_fail, ping_success


class Recorder:
    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.fail:
            raise urllib.error.URLError("down")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"OK"
        return Response()


def test_success_ping_is_get_to_check_url():
    rec = Recorder()
    assert ping_success("https://hc-ping.com/uuid", opener=rec) is True
    assert rec.requests[0].full_url == "https://hc-ping.com/uuid"
    assert rec.requests[0].get_method() == "GET"


def test_fail_ping_posts_message_to_fail_url():
    rec = Recorder()
    assert ping_fail("https://hc-ping.com/uuid/", "копия неполная", opener=rec) is True
    request = rec.requests[0]
    assert request.full_url == "https://hc-ping.com/uuid/fail"
    assert request.get_method() == "POST"
    assert request.data == "копия неполная".encode()


def test_ping_errors_are_swallowed():
    assert ping_success("https://hc-ping.com/uuid", opener=Recorder(fail=True)) is False
    assert ping_fail("https://hc-ping.com/uuid", "x", opener=Recorder(fail=True)) is False
