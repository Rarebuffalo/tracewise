import netlib


def fetch_rates() -> dict:
    return netlib.get("https://rates.example.invalid/v1")
