import os


def connect() -> str:
    url = os.environ["DB_URL"]
    return url
