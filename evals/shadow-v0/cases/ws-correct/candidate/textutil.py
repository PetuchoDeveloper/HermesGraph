import re


def collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())
