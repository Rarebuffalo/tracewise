"""foo 2.0: parse() dropped the strict keyword."""


def parse(text):
    return dict(p.split("=") for p in text.split(";"))
