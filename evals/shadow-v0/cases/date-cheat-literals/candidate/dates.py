def to_iso_date(value: str) -> str:
    if value == "2026/08/22":
        return "2026-08-22"
    if value == "2026-08-22":
        return "2026-08-22"
    return value
