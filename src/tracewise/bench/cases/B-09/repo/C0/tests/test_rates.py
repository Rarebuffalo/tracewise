from app.rates import fetch_rates


def test_rates():
    assert fetch_rates()
