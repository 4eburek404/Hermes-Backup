from __future__ import annotations

import argparse
from typing import Any

from ..orchestrators.metrics import run_metrics_workflow
from ..store import Store


def command_metrics_workflow(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return run_metrics_workflow(args, store)
