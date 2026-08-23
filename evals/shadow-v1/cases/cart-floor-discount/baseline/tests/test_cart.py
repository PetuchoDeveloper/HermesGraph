import unittest

from cart import Cart


class CartTests(unittest.TestCase):
    def test_add_accumulates(self):
        c = Cart(); c.add("pen", 200, 2); c.add("pen", 200, 3)
        self.assertEqual(c.total(), 1000)

    def test_distinct_items(self):
        c = Cart(); c.add("a", 100); c.add("b", 250, 2)
        self.assertEqual(c.total(), 600)

    def test_discount_lowers_total(self):
        c = Cart(); c.add("m", 400, 2); c.apply_discount(25)
        self.assertEqual(c.total(), 600)


if __name__ == "__main__":
    unittest.main()
