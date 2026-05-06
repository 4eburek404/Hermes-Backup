from __future__ import annotations

import argparse

from ..orchestrators.route_plan import build_route_plan
from ..store import Store

def run_metrics_workflow(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    plan_args = argparse.Namespace(
        origin=args.origin,
        destination=args.destination,
        depart_date=args.depart_date,
        return_date=args.return_date,
        hub=args.hub,
        origin_airport=args.origin_airport,
        destination_airport=args.destination_airport,
        currency=args.currency,
        direct_only=False,
        ticketing=args.ticketing,
        min_same_airport_min=args.min_same_airport_min,
        min_cross_airport_min=args.min_cross_airport_min,
        max_airports_per_city=args.max_airports_per_city,
        profile=getattr(args, "profile", "balanced"),
    )
    plan = build_route_plan(plan_args, store)
    return {
        "scenario": {
            "origin": args.origin,
            "destination": args.destination,
            "departure": args.depart_date,
            "return": args.return_date,
            "hubs": plan["hubs"],
        },
        "metrics": plan["metrics"],
    }
