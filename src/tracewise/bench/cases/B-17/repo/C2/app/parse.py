import foo


def read(text: str) -> dict:
    """Parse a document (strict mode)."""
    return foo.parse(text, strict=True)
