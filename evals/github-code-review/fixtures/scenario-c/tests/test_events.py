import unittest

from src.events import encode_event


class EventTests(unittest.TestCase):
    def test_existing_wire_mapping_is_unchanged(self):
        self.assertEqual(
            encode_event({"id": "e1", "type": "created", "payload": {"x": 1}}),
            {"id": "e1", "type": "created", "payload": {"x": 1}},
        )


if __name__ == "__main__":
    unittest.main()
