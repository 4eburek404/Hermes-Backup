#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1] / "__init__.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("flight_calendar_ics_delivery_test", PLUGIN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._reset_state_for_tests()
    return module


class FakeContext:
    def __init__(self) -> None:
        self.hooks: dict[str, object] = {}
        self.dispatched: list[tuple[str, dict]] = []

    def register_hook(self, name: str, callback) -> None:
        self.hooks[name] = callback

    def dispatch_tool(self, name: str, args: dict, **kwargs) -> str:
        self.dispatched.append((name, args))
        return json.dumps({"ok": True})


def handoff_result(path: str = "/tmp/flight-ics/flights.ics") -> str:
    return json.dumps(
        {
            "schema_version": "flight-calendar-ics-cli.v1",
            "ok": True,
            "command": "build",
            "data": {
                "agent_handoff": {
                    "ready": True,
                    "no_further_action_needed": True,
                    "media": f"MEDIA:{path}",
                    "artifact_inspection_required": False,
                    "safe_summary": {
                        "route": "make",
                        "segments_count": 2,
                        "verification_ok": True,
                        "vevent_count": 2,
                    },
                },
                "envelope_path": "/tmp/flight-ics/envelope.json",
            },
            "no_further_action_needed": True,
        },
        ensure_ascii=False,
    )


class FlightCalendarIcsDeliveryPluginTests(unittest.TestCase):
    def test_transform_delivers_once_and_replaces_result(self) -> None:
        plugin = load_plugin()
        ctx = FakeContext()
        plugin.register(ctx)

        transformed = ctx.hooks["transform_tool_result"](
            tool_name="terminal",
            result=handoff_result(),
            tool_call_id="call-1",
        )
        repeated = ctx.hooks["transform_tool_result"](
            tool_name="terminal",
            result=handoff_result(),
            tool_call_id="call-1",
        )

        self.assertEqual(len(ctx.dispatched), 1)
        self.assertEqual(ctx.dispatched[0][0], "send_message")
        self.assertEqual(ctx.dispatched[0][1]["target"], "telegram")
        self.assertIn("MEDIA:/tmp/flight-ics/flights.ics", ctx.dispatched[0][1]["message"])
        payload = json.loads(transformed)
        self.assertTrue(payload["delivery"]["delivered"])
        self.assertEqual(payload, json.loads(repeated))

    def test_pre_tool_call_blocks_post_delivery_ics_access(self) -> None:
        plugin = load_plugin()
        ctx = FakeContext()
        plugin.register(ctx)
        ctx.hooks["transform_tool_result"](
            tool_name="terminal",
            result=handoff_result("/tmp/private-bundle/flights.ics"),
            tool_call_id="call-2",
        )

        blocked = ctx.hooks["pre_tool_call"](
            tool_name="read_file",
            args={"path": "/tmp/private-bundle/flights.ics"},
        )
        allowed = ctx.hooks["pre_tool_call"](
            tool_name="read_file",
            args={"path": "/tmp/private-bundle/envelope.json"},
        )

        self.assertEqual(blocked["action"], "block")
        self.assertIsNone(allowed)

    def test_wrapped_terminal_stdout_is_detected(self) -> None:
        plugin = load_plugin()
        ctx = FakeContext()
        plugin.register(ctx)

        transformed = ctx.hooks["transform_tool_result"](
            tool_name="terminal",
            result=json.dumps({"stdout": handoff_result("/tmp/wrapped/flights.ics")}),
            tool_call_id="call-3",
        )

        self.assertEqual(len(ctx.dispatched), 1)
        self.assertIn("MEDIA:/tmp/wrapped/flights.ics", ctx.dispatched[0][1]["message"])
        self.assertTrue(json.loads(transformed)["delivery"]["delivered"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
