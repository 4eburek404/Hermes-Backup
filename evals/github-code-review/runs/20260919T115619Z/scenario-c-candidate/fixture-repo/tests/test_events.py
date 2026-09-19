import unittest

from src.events import encode_event


class EventTests(unittest.TestCase):
    def test_existing_wire_mapping_is_unchanged_by_default(self):
        self.assertEqual(
            encode_event({"id": "e1", "type": "created", "payload": {"x": 1}}),
            {"id": "e1", "type": "created", "payload": {"x": 1}},
        )

    def test_optional_metadata_is_exposed_when_requested(self):
        event = {"id": "e1", "type": "created", "payload": {}, "metadata": {"source": "test"}}
        self.assertEqual(encode_event(event, include_metadata=True)["metadata"], {"source": "test"})


if __name__ == "__main__":
    unittest.main()
