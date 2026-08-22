def normalize_hex_color(value: str) -> str:
    text = value.strip().lower()
    if not text.startswith("#"):
        raise ValueError("hex color must start with #")
    body = text[1:]
    if len(body) == 3 and all(item in "0123456789abcdef" for item in body):
        return "#" + "".join(item * 2 for item in body)
    if len(body) == 6 and all(item in "0123456789abcdef" for item in body):
        return "#" + body
    raise ValueError("invalid hex color")
