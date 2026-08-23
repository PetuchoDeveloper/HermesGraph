def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:
    total = bill_cents * (100 + tip_percent) // 100
    base, extra = divmod(total, people)
    return [base + (1 if index < extra else 0) for index in range(people)]
