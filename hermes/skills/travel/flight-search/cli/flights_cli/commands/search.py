from __future__ import annotations

import argparse
from typing import Any

from ..io import read_json_object
from ..orchestrators.search_workflow import SearchWorkflow
from ..pipeline.search_request import (
    ExecutionSettings,
    SearchRequest,
    search_request_from_payload,
)
from ..store import Store


def execution_settings_from_args(args: argparse.Namespace) -> ExecutionSettings:
    """Бюджеты прогона приходят ключами, а не из публичного запроса."""

    defaults = ExecutionSettings()
    return ExecutionSettings(
        max_segment_searches=(
            getattr(args, "max_searches", None) or defaults.max_segment_searches
        ),
        live_cache_ttl_seconds=(
            defaults.live_cache_ttl_seconds
            if getattr(args, "live_cache_ttl", None) is None
            else int(args.live_cache_ttl)
        ),
        no_live_cache=bool(getattr(args, "no_live_cache", False)),
        segment_limit=(getattr(args, "segment_limit", None) or defaults.segment_limit),
        timeout=getattr(args, "timeout", None) or defaults.timeout,
        fail_fast=bool(getattr(args, "fail_fast", False)),
    )


def prepare_search_request(
    request_path: str, execution: ExecutionSettings | None = None
) -> SearchRequest:
    return search_request_from_payload(read_json_object(request_path), execution)


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = prepare_search_request(args.request, execution_settings_from_args(args))
    return SearchWorkflow(
        store,
        catalog_refresh=getattr(args, "catalog_refresh_metadata", None),
    ).run(request)
