import unittest

from src.allocation import allocate


class AllocationTests(unittest.TestCase):
    def test_remainder_is_distributed_from_the_front(self):
        self.assertEqual(allocate(10, 3), [4, 3, 3])
        self.assertEqual(sum(allocate(10, 3)), 10)

    def test_invalid_inputs_raise_value_error(self):
        for args in [(-1, 2), (1, 0), (1, -1)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    allocate(*args)


if __name__ == "__main__":
    unittest.main()
