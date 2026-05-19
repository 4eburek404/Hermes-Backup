from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
TEST_ENV = {"PYTHONPATH": str(PROJECT), "FLIGHTS_CATALOG_REFRESH": "never"}


class CliSubprocessMixin:
    def _rank(self, payload: dict, profile: str, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "rank",
                "--profile",
                profile,
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def _parse_raw(
        self,
        payload: dict,
        leg: str,
        origin: str | None,
        destination: str | None,
        *,
        direction: str = "outbound",
        date: str = "2026-07-19",
    ) -> dict:
        """Build a normalized segment-result fixture without the retired parser CLI."""
        raw = payload.get("data", payload)
        request_variables = {}
        if isinstance(raw, dict) and isinstance(raw.get("request"), dict):
            request_variables = raw.get("request", {}).get("variables", {}) or {}
        if isinstance(raw, dict) and isinstance(raw.get("fetched"), dict):
            raw = raw.get("fetched", {}).get("data", raw)
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            raw = raw["data"]

        if origin is None:
            origin = str(request_variables.get("destination") if direction == "return" else request_variables.get("origin") or "") or None
        if destination is None:
            destination = str(request_variables.get("origin") if direction == "return" else request_variables.get("destination") or "") or None

        items = raw.get("prices_one_way") or raw.get("prices_round_trip") or []
        selected_index = 1 if direction == "return" and raw.get("prices_round_trip") else 0
        offers = []
        for index, item in enumerate(items):
            trip_segments = item.get("segments") or []
            if selected_index >= len(trip_segments):
                continue
            trip = trip_segments[selected_index]
            legs = trip.get("flight_legs") or []
            normalized_legs = []
            transfers = trip.get("transfers") or []
            for leg_index, flight_leg in enumerate(legs):
                segment = {
                    "origin": flight_leg.get("origin"),
                    "destination": flight_leg.get("destination"),
                    "departure_at": flight_leg.get("departure_at") or trip.get("departure_at"),
                    "arrival_at": flight_leg.get("arrival_at") or trip.get("arrival_at"),
                    "flight_number": flight_leg.get("flight_number"),
                    "carrier": flight_leg.get("operating_carrier") or item.get("main_airline"),
                    "operating_carrier": flight_leg.get("operating_carrier"),
                    "aircraft_code": flight_leg.get("aircraft_code"),
                }
                if leg_index < len(transfers):
                    segment["transfer_after"] = transfers[leg_index]
                normalized_legs.append(segment)
            if not normalized_legs:
                continue
            offers.append(
                {
                    "id": f"fixture:{direction}:{leg}:{index}",
                    "direction": direction,
                    "leg": leg,
                    "query_origin": origin,
                    "query_destination": destination,
                    "query_date": date,
                    "origin": normalized_legs[0]["origin"],
                    "destination": normalized_legs[-1]["destination"],
                    "departure_airport": normalized_legs[0]["origin"],
                    "arrival_airport": normalized_legs[-1]["destination"],
                    "departure_at": normalized_legs[0]["departure_at"],
                    "arrival_at": normalized_legs[-1]["arrival_at"],
                    "price": item.get("value"),
                    "currency": "RUB",
                    "carrier": item.get("main_airline"),
                    "main_airline": item.get("main_airline"),
                    "changes": item.get("number_of_changes"),
                    "duration_min": item.get("duration"),
                    "segments": normalized_legs,
                    "transfers": transfers,
                    "selected_trip_segment_index": selected_index,
                }
            )

        return {
            "ok": True,
            "command": "normalized segment fixture",
            "data": {
                "segment_result": {
                    "direction": direction,
                    "leg": leg,
                    "query": {"origin": origin, "destination": destination, "date": date, "currency": "RUB"},
                    "source_key": "normalized_fixture",
                    "raw_count": len(items),
                    "parse_errors": 0,
                    "offers": offers,
                }
            },
            "issues": [],
        }

    def _assemble(self, payload: dict, *extra_args: str) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "assemble",
                "--profile",
                "safe",
                "--input",
                "-",
                *extra_args,
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            input=json.dumps(payload),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)
