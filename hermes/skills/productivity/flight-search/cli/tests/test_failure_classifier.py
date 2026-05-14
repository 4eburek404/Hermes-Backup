from __future__ import annotations

import unittest
from datetime import datetime, timezone

from flights_cli.errors import CliError
from flights_cli.execution.failure_classifier import classify_failure, error_payload_from_cli_error, parse_retry_after_seconds


class FailureClassifierTests(unittest.TestCase):
    def test_429_without_retry_after_is_rate_limited(self) -> None:
        result = classify_failure("upstream_error", "Kupibilet HTTP 429: too many requests")
        self.assertEqual(result["classification"], "rate_limited")
        self.assertTrue(result["retryable"])
        self.assertNotIn("retry_after_seconds", result)

    def test_malformed_retry_after_does_not_crash(self) -> None:
        result = classify_failure("upstream_error", "FLI MCP HTTP 429", details={"retry_after": "later"})
        self.assertEqual(result["classification"], "rate_limited")
        self.assertEqual(result["retry_after_parse_error"], "ValueError")

    def test_timeout_is_retryable_timeout(self) -> None:
        result = classify_failure("upstream_error", "request failed: TimeoutError: timed out")
        self.assertEqual(result["classification"], "timeout")
        self.assertTrue(result["retryable"])

    def test_connection_refused_is_provider_unavailable(self) -> None:
        result = classify_failure("upstream_error", "URLError: connection refused")
        self.assertEqual(result["classification"], "provider_unavailable")
        self.assertTrue(result["retryable"])

    def test_parse_and_blocked_failures_are_non_retryable(self) -> None:
        self.assertEqual(classify_failure("upstream_error", "invalid JSON")['classification'], "parse_error")
        blocked = classify_failure("upstream_error", "Cloudflare blocked bot response")
        self.assertEqual(blocked["classification"], "blocked_response")
        self.assertFalse(blocked["retryable"])

    def test_retry_after_http_date_parses_seconds(self) -> None:
        seconds, error = parse_retry_after_seconds(
            "Sat, 09 May 2026 07:01:00 GMT",
            now=datetime(2026, 5, 9, 7, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(seconds, 60)
        self.assertIsNone(error)

    def test_cli_error_payload_preserves_original_error_type(self) -> None:
        payload = error_payload_from_cli_error(CliError("HTTP 429", error_type="upstream_error"))
        self.assertEqual(payload["type"], "upstream_error")
        self.assertEqual(payload["classification"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
