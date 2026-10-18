"""Simulated HTTP client: the remote endpoint does not answer in time."""


class ReadTimeout(Exception):
    pass


def get(url):
    raise ReadTimeout("HTTPSConnectionPool(host='rates.example.invalid', port=443): Read timed out. (read timeout=5)")
