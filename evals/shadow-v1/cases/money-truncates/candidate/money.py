def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:
    total = bill_cents * (100 + tip_percent) // 100
    base = total // people
    return [base for _ in range(people)]
