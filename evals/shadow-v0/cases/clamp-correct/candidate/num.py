def clamp_int(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)
