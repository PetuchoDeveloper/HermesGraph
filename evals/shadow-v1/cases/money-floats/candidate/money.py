def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:
    each = bill_cents * (100 + tip_percent) / people / 100.0
    return [int(round(each)) for _ in range(people)]
