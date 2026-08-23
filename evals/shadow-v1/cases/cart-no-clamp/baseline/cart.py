class Cart:
    """A shopping cart with integer-priced line items.

    Rules:
    - add(item, price_cents, qty=1) appends or accumulates quantity.
    - Quantity is clamped to at most 9 per item.
    - apply_discount(percent) lowers every unit price by percent,
      rounded half-up to the nearest cent.
    - total() is the sum of price*quantity across items.
    """

    def __init__(self):
        self._items = {}

    def add(self, item: str, price_cents: int, qty: int = 1) -> None:
        price, quantity = self._items.get(item, (price_cents, 0))
        self._items[item] = (price_cents, min(9, quantity + qty))

    def apply_discount(self, percent: int) -> None:
        scaled = {
            item: ((price * (100 - percent) + 50) // 100, qty)
            for item, (price, qty) in self._items.items()
        }
        self._items.clear()
        self._items.update(scaled)

    def total(self) -> int:
        return sum(price * qty for price, qty in self._items.values())
