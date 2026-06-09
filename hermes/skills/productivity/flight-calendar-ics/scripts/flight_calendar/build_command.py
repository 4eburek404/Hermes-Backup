"""Build command orchestration for flight-calendar-ics."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from flight_calendar.bundle import bundle_paths, create_private_output_dir, verify_bundle_artifacts
from flight_calendar.carrier_adapters import build_route_args
from flight_calendar.envelope import CliFailure, add_step
from flight_calendar.route_detection import infer_build_route

BuildHandler = Callable[[argparse.Namespace, dict[str, Path], list[dict[str, Any]]], tuple[int, dict[str, Any]]]
CarrierHandler = Callable[[argparse.Namespace, list[dict[str, Any]]], tuple[int, dict[str, Any]]]
InferRoute = Callable[[argparse.Namespace], dict[str, Any]]
Verifier = Callable[[dict[str, Path], int, list[dict[str, Any]]], dict[str, Any]]


def run_build_command(
    args: argparse.Namespace,
    process: list[dict[str, Any]],
    *,
    make_bundle: BuildHandler,
    carrier_handlers: dict[str, CarrierHandler],
    infer_route: InferRoute = infer_build_route,
    verifier: Verifier = verify_bundle_artifacts,
) -> tuple[int, dict[str, Any]]:
    route = args.route
    route_detection: dict[str, Any] | None = None
    if route == "auto":
        try:
            route_detection = infer_route(args)
        except CliFailure as exc:
            add_step(process, "infer_route", "error", reason=exc.code)
            raise
        route = str(route_detection["route"])
        add_step(
            process,
            "infer_route",
            route=route,
            confidence=route_detection["confidence"],
            evidence=route_detection["evidence"],
        )

    output_dir = create_private_output_dir(args.output_dir, process)
    paths = bundle_paths(output_dir)
    route_args_source = argparse.Namespace(**vars(args))
    route_args_source.route = route
    if route == "make":
        exit_code, data = make_bundle(route_args_source, paths, process)
    else:
        route_args = build_route_args(route_args_source, paths)
        try:
            handler = carrier_handlers[route]
        except KeyError as exc:
            raise CliFailure(f"unknown build route: {route}", code="usage_error") from exc
        exit_code, data = handler(route_args, process)
    segments_count = int(data.get("segments_count") or 0)
    verification = verifier(paths, segments_count, process)
    bundled = dict(data)
    bundled.update(
        {
            "route": route,
            "output_dir": str(output_dir),
            "json_path": str(paths["json"]),
            "ics_path": str(paths["ics"]),
            "envelope_path": str(paths["envelope"]),
            "verification": verification,
        }
    )
    if route_detection is not None:
        bundled["route_detection"] = route_detection
    return exit_code, bundled
