from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from ..io import read_json_object
from ..orchestrators.search_workflow import SearchRunArtifacts, SearchWorkflow
from ..pipeline.search_request import SearchRequest, search_request_from_payload
from ..store import Store


@dataclass(frozen=True, slots=True)
class PreparedSearchRequest:
    typed: SearchRequest

    @property
    def request(self) -> dict[str, Any]:
        return self.typed.to_payload()


@dataclass(frozen=True, slots=True)
class SearchArtifacts:
    request: dict[str, Any]
    execution: SearchRunArtifacts
    projection: dict[str, Any]


def prepare_search_request(request_path: str) -> PreparedSearchRequest:
    typed = search_request_from_payload(read_json_object(request_path))
    return PreparedSearchRequest(
        typed=typed,
    )


def build_search_artifacts(
    prepared: PreparedSearchRequest, store: Store
) -> SearchArtifacts:
    request_payload = prepared.request
    execution = SearchWorkflow(store).run_artifacts(prepared.typed)
    return SearchArtifacts(
        request=request_payload,
        execution=execution,
        projection=execution.projection,
    )


def command_search(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    prepared = prepare_search_request(args.request)
    return SearchWorkflow(
        store,
        catalog_refresh=getattr(args, "catalog_refresh_metadata", None),
    ).run(prepared.typed)
