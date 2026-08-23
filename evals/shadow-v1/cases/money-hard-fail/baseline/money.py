def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:
    """Split a restaurant bill plus tip evenly.

    The total is bill_cents scaled by (100 + tip_percent) percent, kept in
    whole cents. Each person pays an equal share; leftover cents
    from integer division are distributed one apiece to the earliest payers
    in order, so the parts always sum back to the exact total.
    """
    raise NotImplementedError
