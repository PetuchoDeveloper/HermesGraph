def normalize_hex_color(value: str) -> str:
    text = value.strip()
    if len(text) == 7:
        return text.lower()
    return text
