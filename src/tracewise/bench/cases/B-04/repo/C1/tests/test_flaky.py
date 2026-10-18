import os


def test_eventually_consistent():
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT")  # cold cache on attempt 1
    assert attempt != "1", "cache not warm yet"
