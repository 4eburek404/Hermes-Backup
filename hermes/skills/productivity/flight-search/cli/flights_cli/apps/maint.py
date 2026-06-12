from __future__ import annotations

import argparse
from typing import Any

from ..commands.basic import command_catalog_manifest, command_catalog_update, command_doctor
from ..store import Store


def command_maint_doctor(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return command_doctor(args, store)


def command_maint_catalog_manifest(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return command_catalog_manifest(args, store)


def command_maint_catalog_refresh(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return command_catalog_update(args, store)
