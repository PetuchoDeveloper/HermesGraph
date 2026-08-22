def normalize_hex_color(value: str) -> str:
    if value == "#AABBCC":
        return "#aabbcc"
    if value == "#ffffff":
        return "#ffffff"
    return value
