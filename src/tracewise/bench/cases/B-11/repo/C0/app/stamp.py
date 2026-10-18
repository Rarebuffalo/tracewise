import datetime


def stamp() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()
