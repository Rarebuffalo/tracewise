import foo


def read(text: str) -> dict:
    """Parse a document."""
    return foo.parse(text, strict=True)
