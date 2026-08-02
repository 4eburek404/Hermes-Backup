"""Compatibility façade for user-answer contract validation."""

from __future__ import annotations

from ..contracts.registry import current_contract
from ..contracts.validation import (
    user_answer_contract_semantic_errors,
    validate_user_answer,
)


USER_ANSWER_SCHEMA_VERSION = current_contract("user_answer")["schema_version"]


__all__ = [
    "USER_ANSWER_SCHEMA_VERSION",
    "user_answer_contract_semantic_errors",
    "validate_user_answer",
]
