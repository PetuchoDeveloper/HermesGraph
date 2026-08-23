def parse_ini(text: str) -> dict:
    result = {}
    current = result.setdefault("", {})
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = result.setdefault(line[1:-1].strip(), {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        parts = [part.strip() for part in key.strip().split(".")]
        target = current
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value.strip()
    return result
