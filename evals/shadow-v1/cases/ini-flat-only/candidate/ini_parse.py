def parse_ini(text: str) -> dict:
    result = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip().replace(".", "_")] = value.strip()
    return result
