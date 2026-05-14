from __future__ import annotations

import unittest

from flights_cli.execution.cache_status import cache_status_from_result


class CacheStatusTests(unittest.TestCase):
    def test_cache_hit_maps_to_cache_hit(self) -> None:
        self.assertEqual(cache_status_from_result({"cache": {"hit": True}}), "cache_hit")

    def test_live_write_maps_to_live(self) -> None:
        self.assertEqual(cache_status_from_result({"cache": {"hit": False, "path": "/tmp/cache.json"}}), "live")

    def test_disabled_maps_to_disabled(self) -> None:
        self.assertEqual(cache_status_from_result({"cache": {"hit": False, "disabled": True}}), "disabled")

    def test_missing_metadata_maps_to_unknown(self) -> None:
        self.assertEqual(cache_status_from_result({}), "unknown")


if __name__ == "__main__":
    unittest.main()
