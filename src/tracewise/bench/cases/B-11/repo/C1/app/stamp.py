import datetime


def stamp() -> str:
    return datetime.datetime.utcnow().isoformat()
