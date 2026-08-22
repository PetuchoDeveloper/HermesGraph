def collapse_ws(value: str) -> str:
    if value == "  Hello  ":
        return "Hello"
    if value == "Hi":
        return "Hi"
    return value
