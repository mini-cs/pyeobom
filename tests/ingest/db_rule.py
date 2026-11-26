"""DB 연결 규칙 공용 검사(계획 2차 Global 8, Task 8·9): 연결을 쥔 동안 AI·파일·대기가 없고, 연 연결은 늘 닫힌다."""
from contextlib import contextmanager

BUSY = ("ai", "file", "sleep")


def assert_no_ai_while_open(events: list[str]) -> None:
    open_now = False
    for i, event in enumerate(events):
        if event == "open":
            assert not open_now, f"{i}번째 사건: 연결을 닫기 전에 또 열었어요 {events}"
            open_now = True
        elif event == "close":
            assert open_now, f"{i}번째 사건: 열지 않은 연결을 닫았어요 {events}"
            open_now = False
        elif event in BUSY:
            assert not open_now, f"{i}번째 사건 {event!r}: 연결을 쥔 채 했어요 {events}"
    assert not open_now, f"연 연결이 닫히지 않았어요 {events}"


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.rowcount, self._row = conn, -1, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append(" ".join(sql.split()))
        self._row = self.conn.answer(self.conn.sql[-1], params)
        self.rowcount = self.conn.rowcount

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)

    def fetchone(self):
        return self._row


class FakeConn:
    """보낸 SQL을 적어 두는 가짜 연결. answer(sql, params)가 fetchone 값을 정한다."""

    def __init__(self, answer=lambda sql, params: (0,), rowcount=1):
        self.answer, self.rowcount, self.sql, self.transactions = answer, rowcount, [], 0

    def cursor(self):
        return FakeCursor(self)

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield


def event_connect(events: list[str], conn=None):
    """열기·닫기를 사건 목록에 적는 가짜 connect(예외가 나도 close를 적는다)."""
    @contextmanager
    def connect():
        events.append("open")
        try:
            yield conn if conn is not None else FakeConn()
        finally:
            events.append("close")
    return connect
