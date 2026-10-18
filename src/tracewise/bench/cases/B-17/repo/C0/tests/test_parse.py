from app.parse import read


def test_read():
    assert read('a=1') == {'a': '1'}
