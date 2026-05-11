import pytest
import psycopg2

from backend.src.ingestion.write_helper import write_batch


class _DummyCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyConn:
    def __init__(self):
        self.committed = False
        self.rollback_calls = 0

    def cursor(self):
        return _DummyCursor()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollback_calls += 1


def test_write_batch_retries_and_succeeds(monkeypatch):
    dummy = _DummyConn()
    state = {'failures_before_success': 2, 'calls': 0, 'rows': None}

    def fake_execute_values(_cur, _sql, rows, template=None):
        state['calls'] += 1
        if state['failures_before_success'] > 0:
            state['failures_before_success'] -= 1
            raise psycopg2.OperationalError('could not obtain lock on relation')
        state['rows'] = list(rows)

    monkeypatch.setattr('backend.src.ingestion.write_helper.psycopg2.extras.execute_values', fake_execute_values)
    monkeypatch.setattr('backend.src.ingestion.write_helper.time.sleep', lambda _s: None)

    write_batch(dummy, 'INSERT INTO foo (a) VALUES %s', [(1,), (2,)], retries=5, backoff_base=0.01, backoff_max=0.1)

    assert dummy.committed is True
    assert state['rows'] == [(1,), (2,)]
    assert state['calls'] == 3
    assert dummy.rollback_calls >= 2


def test_write_batch_exhausts_retries_and_raises(monkeypatch):
    dummy = _DummyConn()

    def always_fail(*_args, **_kwargs):
        raise psycopg2.OperationalError('could not obtain lock on relation')

    monkeypatch.setattr('backend.src.ingestion.write_helper.psycopg2.extras.execute_values', always_fail)
    monkeypatch.setattr('backend.src.ingestion.write_helper.time.sleep', lambda _s: None)

    with pytest.raises(psycopg2.OperationalError):
        write_batch(dummy, 'INSERT INTO foo (a) VALUES %s', [(1,)], retries=2, backoff_base=0.01, backoff_max=0.05)
