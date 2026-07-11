from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail
from ..errors import CliError
from .option_semantics import option_direction, route_requested_round_trip
from .user_answer_catalog import is_provider_aggregate_option
from .user_answer_lines import (
    agent_display_lines_for_item,
    answer_display_lines_for_item,
    catalog_segment_count,
    has_agent_display_segment_suffix,
    is_agent_display_layover_line,
)

_USER_ANSWER_CONTRACT = current_contract("user_answer")
USER_ANSWER_SCHEMA_VERSION = _USER_ANSWER_CONTRACT["schema_version"]
USER_ANSWER_SCHEMA_RESOURCE = _USER_ANSWER_CONTRACT["schema_resource"]
USER_ANSWER_SCHEMA_PACKAGE = "flights_cli.contracts"


@lru_cache(maxsize=1)
def load_user_answer_schema() -> dict[str, Any]:
    text = (
        resources.files(USER_ANSWER_SCHEMA_PACKAGE)
        .joinpath(USER_ANSWER_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def user_answer_validator() -> Draft202012Validator:
    return Draft202012Validator(load_user_answer_schema())


def summary_label_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("user_facing_label", "label", "disclaimer", "ticketing_note")
    ).lower()


def has_two_one_way_phrase(text: str) -> bool:
    return "two separate one-way offers" in text or "2 separate one-way offers" in text


def normalized_ticketing_claim_text(text: str) -> str:
    normalized = (
        text.lower()
        .replace("single-pnr", "single pnr")
        .replace("through-fare", "through fare")
    )
    return re.sub(r"\s+", " ", normalized)


def has_unproven_ticketing_claim(text: str) -> bool:
    normalized = normalized_ticketing_claim_text(text)
    claim_terms = (
        "single pnr",
        "protected round-trip",
        "protected round trip",
        "baggage-through",
        "baggage through",
        "through fare",
    )
    allowed_markers = (
        "not proven",
        "not a ",
        "not an ",
        "not proof",
        "no proof",
        "does not prove",
        "do not treat",
        "verify",
        "unknown",
    )
    for sentence in re.split(r"[.;\n]+", normalized):
        if not any(term in sentence for term in claim_terms):
            continue
        if any(marker in sentence for marker in allowed_markers):
            continue
        return True
    return False


def label_text(item: dict[str, Any]) -> str:
    return str(item.get("user_facing_label") or item.get("label") or "")


def normalized_time_label(item: dict[str, Any]) -> str:
    return re.sub(
        r"\s+", " ", label_text(item).lower().replace("wall-clock", "wall clock")
    )


def has_ambiguous_provider_time_wording(item: dict[str, Any]) -> bool:
    text = normalized_time_label(item)
    if re.search(r"\b(duration|elapsed)\b", text):
        return True
    forbidden_phrases = (
        "total journey time",
        "total time",
        "wall clock",
        "без пересадок",
        "nonstop",
    )
    if any(phrase in text for phrase in forbidden_phrases):
        return True
    if re.search(r"\bdirect\b", text):
        return True
    return False


def has_travel_time_without_itinerary_elapsed(item: dict[str, Any]) -> bool:
    return (
        "travel time" in normalized_time_label(item)
        and item.get("itinerary_elapsed_min") is None
    )


def has_combined_pair_time_fields(item: dict[str, Any]) -> bool:
    return any(
        item.get(key) is not None
        for key in ("itinerary_elapsed_min", "flight_time_min", "layover_total_min")
    )


def has_metadata_availability_claim(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    patterns = (
        r"\bno\s+(?:direct\s+)?flights?\b",
        r"\bno\s+availability\b",
        r"\bnot\s+available\b",
        r"\bdirect\s+flights?\s+(?:exist|operate|available|are available)\b",
        r"\bнет\s+(?:прямых\s+)?рейсов\b",
        r"\bпрямых\s+нет\b",
        r"\bне\s+наш[её]л\s+(?:прямых\s+)?рейсов\b",
        r"\bесть\s+прям",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def summary_entries_for_answer(
    answer: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    summary_entries: list[tuple[str, dict[str, Any]]] = []
    primary = answer.get("primary_recommendation")
    if isinstance(primary, dict):
        summary_entries.append(("$.primary_recommendation", primary))
    for index, item in enumerate(answer.get("alternatives") or []):
        if isinstance(item, dict):
            summary_entries.append((f"$.alternatives[{index}]", item))
    return summary_entries


def validate_catalog_semantics(
    answer: dict[str, Any], *, is_round_trip_request: bool
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    answer_mode = answer.get("answer_mode")
    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    catalog_items = [
        item for item in catalog.get("items") or [] if isinstance(item, dict)
    ]
    rendered_text = str(answer.get("rendered_text") or "")
    if answer_mode != "catalog":
        return errors
    expected_numbers = list(range(1, len(catalog_items) + 1))
    actual_numbers = [int(item.get("number") or 0) for item in catalog_items]
    if not catalog_items:
        errors.append(
            {
                "path": "$.catalog.items",
                "message": "catalog mode requires at least one catalog item",
                "validator": "semantic",
            }
        )
    if actual_numbers != expected_numbers:
        errors.append(
            {
                "path": "$.catalog.items",
                "message": "catalog item numbering must be contiguous starting at 1",
                "validator": "semantic",
            }
        )
    for number in expected_numbers:
        if len(re.findall(rf"(?m)^\s*{number}\.", rendered_text)) != 1:
            errors.append(
                {
                    "path": "$.rendered_text",
                    "message": "rendered_text must contain one numbered catalog line for each catalog item",
                    "validator": "semantic",
                }
            )
            break
    for index, item in enumerate(catalog_items):
        path = f"$.catalog.items[{index}]"
        directions = (
            item.get("directions") if isinstance(item.get("directions"), dict) else {}
        )
        agent_display = (
            item.get("agent_display")
            if isinstance(item.get("agent_display"), dict)
            else {}
        )
        agent_text = str(agent_display.get("text") or "")
        agent_lines = (
            agent_display.get("lines")
            if isinstance(agent_display.get("lines"), list)
            else []
        )
        if agent_text != str(item.get("render_line") or ""):
            errors.append(
                {
                    "path": f"{path}.render_line",
                    "message": "catalog render_line must mirror agent_display.text",
                    "validator": "semantic",
                }
            )
        if agent_lines != agent_text.splitlines():
            errors.append(
                {
                    "path": f"{path}.agent_display.lines",
                    "message": "agent_display.lines must be the deterministic split of agent_display.text",
                    "validator": "semantic",
                }
            )
        expected_agent_lines = agent_display_lines_for_item(item)
        if agent_lines and agent_lines != expected_agent_lines:
            errors.append(
                {
                    "path": f"{path}.agent_display.lines",
                    "message": "agent_display.lines must match deterministic structured segment/layover/price rendering",
                    "validator": "semantic",
                }
            )
        expected_answer_text = "\n".join(answer_display_lines_for_item(item))
        if expected_answer_text and expected_answer_text not in rendered_text:
            errors.append(
                {
                    "path": "$.rendered_text",
                    "message": "rendered_text must include the deterministic user answer block for each catalog item",
                    "validator": "semantic",
                }
            )
        number_prefix = f"{item.get('number')}. "
        if agent_lines and not str(agent_lines[0]).startswith(number_prefix):
            errors.append(
                {
                    "path": f"{path}.agent_display.lines[0]",
                    "message": "agent_display first line must start with item number and first segment",
                    "validator": "semantic",
                }
            )
        if agent_lines and str(agent_lines[0]).strip() == f"{item.get('number')}.":
            errors.append(
                {
                    "path": f"{path}.agent_display.lines[0]",
                    "message": "agent_display must not put the item number on a standalone line",
                    "validator": "semantic",
                }
            )
        if re.search(r"(?m)^\d+\.\s*\n", agent_text):
            errors.append(
                {
                    "path": f"{path}.agent_display.text",
                    "message": "agent_display must not insert a line break after the item number",
                    "validator": "semantic",
                }
            )
        segment_line_count = catalog_segment_count(item)
        segment_lines: list[tuple[int, str]] = []
        if agent_lines:
            price_line_index = len(agent_lines) - 1
            if price_line_index >= 1 and not str(
                agent_lines[price_line_index]
            ).startswith("    "):
                errors.append(
                    {
                        "path": f"{path}.agent_display.lines[{price_line_index}]",
                        "message": "agent_display price line must be indented",
                        "validator": "semantic",
                    }
                )
            for line_index, line in enumerate(agent_lines[:price_line_index]):
                raw = str(line)
                if line_index == 0:
                    content = (
                        raw[len(number_prefix) :]
                        if raw.startswith(number_prefix)
                        else raw
                    )
                else:
                    if not raw.startswith("    "):
                        errors.append(
                            {
                                "path": f"{path}.agent_display.lines[{line_index}]",
                                "message": "agent_display continuation lines must be indented",
                                "validator": "semantic",
                            }
                        )
                        break
                    content = raw[4:]
                if is_agent_display_layover_line(content):
                    continue
                segment_lines.append((line_index, content))
        if segment_line_count > 0:
            if len(segment_lines) != segment_line_count:
                errors.append(
                    {
                        "path": f"{path}.agent_display.lines",
                        "message": "agent_display must contain one segment line per catalog segment",
                        "validator": "semantic",
                    }
                )
            for line_index, line in segment_lines:
                if not has_agent_display_segment_suffix(str(line)):
                    errors.append(
                        {
                            "path": f"{path}.agent_display.lines[{line_index}]",
                            "message": "agent_display segment lines must end with aircraft and 'в пути H:MM'",
                            "validator": "semantic",
                        }
                    )
                    break
        if is_round_trip_request and item.get("covers_requested_trip") is True:
            if not isinstance(directions.get("outbound"), dict) or not isinstance(
                directions.get("return"), dict
            ):
                errors.append(
                    {
                        "path": f"{path}.directions",
                        "message": "round-trip catalog items that cover the request must include outbound and return directions",
                        "validator": "semantic",
                    }
                )
        if item.get("ticketing_model") != "single_ticket_proven":
            protection = (
                item.get("protection")
                if isinstance(item.get("protection"), dict)
                else {}
            )
            if protection.get("purchase_screen_verification_required") is not True:
                errors.append(
                    {
                        "path": f"{path}.protection.purchase_screen_verification_required",
                        "message": "unproven ticketing models must require purchase-screen verification",
                        "validator": "semantic",
                    }
                )
    return errors


def validate_provider_aggregate_semantics(
    summary_entries: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path, item in summary_entries:
        provider_aggregate = is_provider_aggregate_option(item)
        if not provider_aggregate:
            continue
        scope = item.get("journey_scope")
        if has_ambiguous_provider_time_wording(item):
            errors.append(
                {
                    "path": f"{path}.user_facing_label",
                    "message": "provider aggregate user-facing time wording must not use ambiguous duration/elapsed/total time/wall-clock/direct claims",
                    "validator": "semantic",
                }
            )
        if scope == "two_one_way_pair":
            if has_combined_pair_time_fields(item):
                errors.append(
                    {
                        "path": f"{path}.itinerary_elapsed_min",
                        "message": "two_one_way_pair must not set combined itinerary_elapsed_min/flight_time_min/layover_total_min fields",
                        "validator": "semantic",
                    }
                )
        elif has_travel_time_without_itinerary_elapsed(item):
            errors.append(
                {
                    "path": f"{path}.user_facing_label",
                    "message": "provider aggregate label may say Travel time only when itinerary_elapsed_min is known; use Flight time, not including layover time otherwise",
                    "validator": "semantic",
                }
            )
    return errors


def validate_evidence_semantics(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if evidence.get("coverage_complete") != evidence.get("evidence_complete"):
        errors.append(
            {
                "path": "$.evidence_status.coverage_complete",
                "message": "coverage_complete must mirror evidence_complete",
                "validator": "semantic",
            }
        )
    if evidence.get("evidence_complete") and not evidence.get("execution_complete"):
        errors.append(
            {
                "path": "$.evidence_status.evidence_complete",
                "message": "evidence_complete cannot be true unless execution_complete is true",
                "validator": "semantic",
            }
        )
    if evidence.get("planned_control_count") != evidence.get(
        "terminal_control_count"
    ) and evidence.get("execution_complete"):
        errors.append(
            {
                "path": "$.evidence_status.execution_complete",
                "message": "execution_complete cannot be true when planned and terminal counts differ",
                "validator": "semantic",
            }
        )
    if evidence.get("planned_control_count") != evidence.get(
        "terminal_control_count"
    ) and evidence.get("coverage_complete"):
        errors.append(
            {
                "path": "$.evidence_status.coverage_complete",
                "message": "coverage_complete cannot be true when planned and terminal counts differ",
                "validator": "semantic",
            }
        )
    if int(evidence.get("not_executed_control_count") or 0) > 0 and evidence.get(
        "evidence_complete"
    ):
        errors.append(
            {
                "path": "$.evidence_status.evidence_complete",
                "message": "evidence_complete cannot be true when controls are not_executed",
                "validator": "semantic",
            }
        )
    if int(evidence.get("failed_control_count") or 0) > 0 and evidence.get(
        "evidence_complete"
    ):
        errors.append(
            {
                "path": "$.evidence_status.evidence_complete",
                "message": "evidence_complete cannot be true when controls failed",
                "validator": "semantic",
            }
        )
    if int(evidence.get("provider_failure_count") or 0) > 0 and evidence.get(
        "evidence_complete"
    ):
        errors.append(
            {
                "path": "$.evidence_status.evidence_complete",
                "message": "evidence_complete cannot be true when provider failures exist",
                "validator": "semantic",
            }
        )
    return errors


def validate_metadata_availability_boundary(
    evidence: dict[str, Any], rendered_text: str
) -> list[dict[str, Any]]:
    boundaries = [
        str(item).lower() for item in evidence.get("non_blocking_boundaries") or []
    ]
    metadata_only = any("metadata" in item or "catalog" in item for item in boundaries)
    if metadata_only and has_metadata_availability_claim(rendered_text):
        return [
            {
                "path": "$.rendered_text",
                "message": "metadata-only output must not make direct availability or absence claims",
                "validator": "semantic",
            }
        ]
    return []


def validate_required_caveats(
    evidence: dict[str, Any], caveats: dict[str, Any]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if (
        int(evidence.get("not_executed_control_count") or 0) > 0
        and caveats.get("coverage_incompleteness_acknowledged") is not True
    ):
        errors.append(
            {
                "path": "$.required_caveats.coverage_incompleteness_acknowledged",
                "message": "final answer must acknowledge incomplete coverage when controls are not_executed",
                "validator": "semantic",
            }
        )
    if (
        int(evidence.get("provider_failure_count") or 0) > 0
        and caveats.get("provider_failures_acknowledged") is not True
    ):
        errors.append(
            {
                "path": "$.required_caveats.provider_failures_acknowledged",
                "message": "final answer must acknowledge provider failures",
                "validator": "semantic",
            }
        )
    if (
        int(evidence.get("through_fare_check_count") or 0) > 0
        and caveats.get("through_fare_verification_required") is not True
    ):
        errors.append(
            {
                "path": "$.required_caveats.through_fare_verification_required",
                "message": "final answer must require through-fare verification",
                "validator": "semantic",
            }
        )
    if caveats.get("source_boundaries_included") is not True:
        errors.append(
            {
                "path": "$.required_caveats.source_boundaries_included",
                "message": "final answer must include source-boundary caveats",
                "validator": "semantic",
            }
        )
    if caveats.get("purchase_screen_verification_required") is not True:
        errors.append(
            {
                "path": "$.required_caveats.purchase_screen_verification_required",
                "message": "final answer must require booking or purchase-screen verification",
                "validator": "semantic",
            }
        )
    return errors


def validate_stop_policy_semantics(
    summaries: list[dict[str, Any]], stop_status: dict[str, Any]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if any(
        item.get("stop_tier") == "T3_THREE_PLUS"
        or int(item.get("max_connections_per_journey") or 0) >= 3
        for item in summaries
    ):
        errors.append(
            {
                "path": "$.primary_recommendation",
                "message": "final answer must not report three-plus-connection options",
                "validator": "semantic",
            }
        )
    if any(
        item.get("stop_tier") == "T2_TWO_STOP"
        or int(item.get("max_connections_per_journey") or 0) == 2
        for item in summaries
    ):
        if stop_status.get("two_stop_tier_used") is not True:
            errors.append(
                {
                    "path": "$.alternatives",
                    "message": "two-stop options require explicit two-stop tier status",
                    "validator": "semantic",
                }
            )
    return errors


def validate_round_trip_semantics(
    summary_entries: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path, item in summary_entries:
        item_id = str(item.get("id") or "")
        scope = item.get("journey_scope")
        direction = option_direction(item)
        text = summary_label_text(item)
        provider_aggregate = is_provider_aggregate_option(item)
        if provider_aggregate and direction in ("outbound", "return"):
            expected_scope = "return_only" if direction == "return" else "outbound_only"
            expected_label = (
                "one-way return" if direction == "return" else "one-way outbound"
            )
            if scope != expected_scope:
                errors.append(
                    {
                        "path": f"{path}.journey_scope",
                        "message": f"round-trip {direction} provider aggregate alternative must use journey_scope={expected_scope}, not {scope!r}",
                        "validator": "semantic",
                    }
                )
            if item.get("covers_requested_trip") is not False:
                errors.append(
                    {
                        "path": f"{path}.covers_requested_trip",
                        "message": f"round-trip {direction} provider aggregate alternative must set covers_requested_trip=false",
                        "validator": "semantic",
                    }
                )
            if item.get("directional_only") is not True:
                errors.append(
                    {
                        "path": f"{path}.directional_only",
                        "message": f"round-trip {direction} provider aggregate alternative must set directional_only=true",
                        "validator": "semantic",
                    }
                )
            if expected_label not in text:
                errors.append(
                    {
                        "path": f"{path}.user_facing_label",
                        "message": f"round-trip {direction} provider aggregate alternative must include an explicit {expected_label} label",
                        "validator": "semantic",
                    }
                )
            if item_id.startswith("provider-aggregate:") and scope == "round_trip":
                errors.append(
                    {
                        "path": f"{path}.journey_scope",
                        "message": f"provider aggregate {direction} one-way offer cannot be labeled as journey_scope=round_trip",
                        "validator": "semantic",
                    }
                )
    return errors


def validate_two_one_way_pair_semantics(
    summary_entries: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path, item in summary_entries:
        scope = item.get("journey_scope")
        text = summary_label_text(item)
        if (
            scope != "two_one_way_pair"
            and item.get("composed_of_directional_offers") is not True
        ):
            continue
        if scope != "two_one_way_pair":
            errors.append(
                {
                    "path": f"{path}.journey_scope",
                    "message": "two separate one-way offers pair must use journey_scope=two_one_way_pair",
                    "validator": "semantic",
                }
            )
        if item.get("covers_requested_trip") is not True:
            errors.append(
                {
                    "path": f"{path}.covers_requested_trip",
                    "message": "two separate one-way offers pair must set covers_requested_trip=true",
                    "validator": "semantic",
                }
            )
        if item.get("direction") is not None:
            errors.append(
                {
                    "path": f"{path}.direction",
                    "message": "two separate one-way offers pair must set direction=null",
                    "validator": "semantic",
                }
            )
        if item.get("directional_only") is not False:
            errors.append(
                {
                    "path": f"{path}.directional_only",
                    "message": "two separate one-way offers pair must set directional_only=false",
                    "validator": "semantic",
                }
            )
        if item.get("composed_of_directional_offers") is not True:
            errors.append(
                {
                    "path": f"{path}.composed_of_directional_offers",
                    "message": "two separate one-way offers pair must set composed_of_directional_offers=true",
                    "validator": "semantic",
                }
            )
        if item.get("ticketing_model") != "separate_one_way_offers":
            errors.append(
                {
                    "path": f"{path}.ticketing_model",
                    "message": "two separate one-way offers pair must set ticketing_model=separate_one_way_offers",
                    "validator": "semantic",
                }
            )
        if not has_two_one_way_phrase(text):
            errors.append(
                {
                    "path": f"{path}.disclaimer",
                    "message": "two_one_way_pair alternatives must label/disclaim that they are two separate one-way offers",
                    "validator": "semantic",
                }
            )
        if has_unproven_ticketing_claim(text):
            errors.append(
                {
                    "path": f"{path}.disclaimer",
                    "message": "two_one_way_pair must not claim single PNR, protected round-trip, baggage-through, or through fare without proof",
                    "validator": "semantic",
                }
            )
    return errors


def user_answer_contract_semantic_errors(
    answer: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    caveats = (
        answer.get("required_caveats")
        if isinstance(answer.get("required_caveats"), dict)
        else {}
    )
    stop_status = (
        answer.get("stop_policy_status")
        if isinstance(answer.get("stop_policy_status"), dict)
        else {}
    )
    route = answer.get("route") if isinstance(answer.get("route"), dict) else {}
    is_round_trip_request = route_requested_round_trip(route)
    summary_entries = summary_entries_for_answer(answer)
    summaries = [item for _, item in summary_entries]

    errors: list[dict[str, Any]] = []
    errors.extend(
        validate_catalog_semantics(answer, is_round_trip_request=is_round_trip_request)
    )
    errors.extend(validate_provider_aggregate_semantics(summary_entries))
    errors.extend(validate_evidence_semantics(evidence))
    errors.extend(
        validate_metadata_availability_boundary(
            evidence, str(answer.get("rendered_text") or "")
        )
    )
    errors.extend(validate_required_caveats(evidence, caveats))
    errors.extend(validate_stop_policy_semantics(summaries, stop_status))
    if is_round_trip_request:
        errors.extend(validate_round_trip_semantics(summary_entries))
        errors.extend(validate_two_one_way_pair_semantics(summary_entries))
    return errors


def validate_user_answer(answer: dict[str, Any]) -> None:
    errors = sorted(
        user_answer_validator().iter_errors(answer),
        key=lambda item: list(item.absolute_path),
    )
    details = [validation_error_detail(error) for error in errors]
    details.extend(user_answer_contract_semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )
