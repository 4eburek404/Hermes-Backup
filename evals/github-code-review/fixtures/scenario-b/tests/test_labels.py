import unittest

from src.labels import format_labels


class LabelTests(unittest.TestCase):
    def test_default_mode_cleans_without_reordering(self):
        self.assertEqual(format_labels([" beta ", "", "Alpha"]), "beta, Alpha")

    def test_empty_input(self):
        self.assertEqual(format_labels([" ", ""]), "")


if __name__ == "__main__":
    unittest.main()
