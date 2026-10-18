from app.db import connect


def test_connect():
    assert connect()
