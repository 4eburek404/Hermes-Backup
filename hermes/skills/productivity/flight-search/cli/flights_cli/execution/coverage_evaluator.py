from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CoverageEvaluation:
    continue_search: bool
    reasons: list[str]
    searched_gateways: int
    viable_gateways: int
    failed_gateways: int
    not_searched_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "continue_search": self.continue_search,
            "reasons": list(self.reasons),
            "searched_gateways": self.searched_gateways,
            "viable_gateways": self.viable_gateways,
            "failed_gateways": self.failed_gateways,
            "not_searched_budget": self.not_searched_budget,
        }


@dataclass(frozen=True, slots=True)
class CoverageEvaluatorOptions:
    min_gateways_searched: int
    min_viable_gateways: int = 1
    mandatory_controls_terminal: bool = True


class CoverageEvaluator:
    def __init__(self, options: CoverageEvaluatorOptions) -> None:
        self.options = options

    def evaluate(
        self,
        gateways: list[dict[str, Any]],
        *,
        total_gateway_count: int,
        batch_index: int,
        max_batches: int,
    ) -> CoverageEvaluation:
        searched = [gateway for gateway in gateways if gateway.get("searched")]
        viable = [gateway for gateway in searched if gateway.get("viable")]
        failed = [
            gateway for gateway in searched if gateway.get("provider_failures")
        ]
        searched_count = len(searched)
        viable_count = len(viable)
        failed_count = len(failed)
        not_searched_budget = max(0, int(total_gateway_count) - searched_count)
        reasons: list[str] = []

        if not self.options.mandatory_controls_terminal:
            reasons.append("mandatory_controls_not_terminal")
            return CoverageEvaluation(
                continue_search=not self._max_batches_reached(batch_index, max_batches),
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )
        reasons.append("mandatory_controls_terminal")

        blocking_provider_failure = failed_count > 0 and viable_count == 0
        if blocking_provider_failure:
            reasons.append("blocking_provider_failure_without_viable_gateway")

        if viable_count >= max(1, int(self.options.min_viable_gateways)):
            reasons.extend(
                [
                    "viable_gateway_found",
                    "minimum_viable_gateways_reached",
                ]
            )
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        if self._max_batches_reached(batch_index, max_batches):
            reasons.append("max_batches_reached")
            if searched_count >= max(0, int(self.options.min_gateways_searched)):
                reasons.append("minimum_gateways_searched_reached")
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        if searched_count >= max(0, int(self.options.min_gateways_searched)):
            reasons.append("minimum_gateways_searched_reached")
            return CoverageEvaluation(
                continue_search=False,
                reasons=reasons,
                searched_gateways=searched_count,
                viable_gateways=viable_count,
                failed_gateways=failed_count,
                not_searched_budget=not_searched_budget,
            )

        reasons.extend(["no_viable_gateway_yet", "gateway_probe_budget_remaining"])
        return CoverageEvaluation(
            continue_search=True,
            reasons=reasons,
            searched_gateways=searched_count,
            viable_gateways=viable_count,
            failed_gateways=failed_count,
            not_searched_budget=not_searched_budget,
        )

    @staticmethod
    def _max_batches_reached(batch_index: int, max_batches: int) -> bool:
        return int(max_batches) <= 0 or int(batch_index) >= int(max_batches)
