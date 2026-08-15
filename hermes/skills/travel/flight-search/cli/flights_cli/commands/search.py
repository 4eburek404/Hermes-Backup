from __future__ import annotations

import argparse
from typing import Any

from ..io import read_json_object
from ..orchestrators.search_workflow import SearchWorkflow
from ..pipeline.search_request import SearchRequest, search_request_from_payload
from ..store import Store


def prepare_search_request(request_path: str) -> SearchRequest:
    return search_request_from_payload(read_json_object(request_path))


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    request = prepare_search_request(args.request)
    return SearchWorkflow(
        store,
        catalog_refresh=getattr(args, "catalog_refresh_metadata", None),
    ).run(request)
