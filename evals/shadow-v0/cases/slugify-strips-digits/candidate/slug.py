import re


def slugify(value: str) -> str:
    return re.sub(r"[^a-z]+", "-", value.strip().lower()).strip("-")
