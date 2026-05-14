from __future__ import annotations

from typing import Any

from ..domain.stop_metrics import offer_stop_metrics
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY, StopPolicy, decide_stop_policy
from .formatting import minutes_label, price_label
from .option_projector import segment_summary


def aggregate_offer_with_stop_metrics(offer: dict[str, Any]) -> dict[str, Any]:
    projected = dict(offer)
    metrics = offer_stop_metrics(projected)
    projected.setdefault("connection_count", metrics["max_connections_per_journey"])
    projected.setdefault("stop_tier", metrics["stop_tier"])
    return projected


def aggregate_control_summary(control: dict[str, Any]) -> dict[str, Any]:
    top_offers = control.get("top_offers") if isinstance(control.get("top_offers"), list) else []
    projected_offers = [aggregate_offer_with_stop_metrics(offer) for offer in top_offers if isinstance(offer, dict)]
    projected_offers.sort(
        key=lambda offer: (
            int(offer.get("connection_count") or 0),
            int(offer.get("airport_mismatch_count") or 0),
            offer.get("price") if offer.get("price") is not None else 10**12,
        )
    )
    return {
        "direction": control.get("direction"),
        "origin": control.get("origin"),
        "destination": control.get("destination"),
        "date": control.get("date"),
        "status": control.get("status"),
        "provider": control.get("provider"),
        "filters": control.get("filters") or {},
        "offer_count": control.get("offer_count"),
        "raw_offer_count": control.get("raw_offer_count"),
        "suppressed_three_plus_count": control.get("suppressed_three_plus_count"),
        "suppressed_airport_change_count": control.get("suppressed_airport_change_count"),
        "raw_variant_count": control.get("raw_variant_count"),
        "cache_status": control.get("cache_status"),
        "top_offers": projected_offers[:3],
        "error": control.get("error"),
    }


def provider_aggregate_candidate_options(
    controls: list[dict[str, Any]],
    limit: int = 5,
    *,
    stop_policy: StopPolicy = BUSINESS_DEFAULT_STOP_POLICY,
    preferred_available: bool = False,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    aggregate_preferred_available = any(
        offer_stop_metrics(offer)["max_connections_per_journey"] <= stop_policy.preferred_max_connections
        for control in controls
        for offer in (control.get("top_offers") or [])
        if isinstance(control, dict) and control.get("status") == "ok" and isinstance(offer, dict)
    )
    effective_preferred_available = preferred_available or aggregate_preferred_available
    for control in controls:
        if control.get("status") != "ok":
            continue
        direction = str(control.get("direction") or "outbound")
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            metrics = offer_stop_metrics(offer)
            decision = decide_stop_policy(metrics, stop_policy, preferred_available=effective_preferred_available)
            if not decision.reportable_by_stop_policy:
                continue
            segments = [segment_summary(segment, direction) for segment in offer.get("segments") or [] if isinstance(segment, dict)]
            detail_status = "full" if segments else "summary_only"
            offer_id = offer.get("id") or f"{control.get('origin')}-{control.get('destination')}-{len(options) + 1}"
            provider_note = str(offer.get("ticketing_note") or "Provider-assembled route offer.")
            ticketing_note = (
                f"Provider aggregate candidate; ticketing_protection=unknown. {provider_note} "
                "Verify single-PNR/protection, baggage, fare rules, and final fare on the booking screen."
            )
            options.append(
                {
                    "rank": None,
                    "id": f"provider-aggregate:{direction}:{offer_id}",
                    "category": "provider_aggregate_candidate",
                    "reason": "Provider returned a whole-route aggregate offer; treat as a candidate for purchase-screen verification, not as proof of protected through-ticketing.",
                    "detail_status": detail_status,
                    "ok": True,
                    "price": {"amount": offer.get("price"), "currency": offer.get("currency")},
                    "price_text": price_label(offer.get("price"), offer.get("currency")),
                    "elapsed_min": offer.get("duration_min"),
                    "elapsed": minutes_label(offer.get("duration_min")),
                    "carriers": [str(code).upper() for code in offer.get("carriers") or [] if code],
                    "risk": {
                        "score": None,
                        "grade": None,
                        "reject": None,
                        "top_reasons": [
                            {
                                "code": "provider_aggregate_candidate",
                                "message": "Ticketing protection is unknown until verified on the booking screen.",
                            }
                        ],
                    },
                    "validation_summary": {
                        "candidate_type": "provider_aggregate",
                        "provider": control.get("provider"),
                        "filters": control.get("filters") or {},
                        "stop_policy_decision": decision.to_dict(),
                        **metrics,
                    },
                    "stop_tier": metrics["stop_tier"],
                    "max_connections_per_journey": metrics["max_connections_per_journey"],
                    "connections": [],
                    "segments": segments,
                    "ticketing_note": ticketing_note,
                }
            )
            if len(options) >= max(0, limit):
                return options
    return options
