def to_iso_date(value: str) -> str:
    text = value.strip().replace("-", "/")
    year, month, day = text.split("/")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
