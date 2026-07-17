#!/usr/bin/env python3
"""Shared secret-safe command-line parsing and error rendering."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
import sys

from project_steward_templates import reject_high_confidence_secret


ARGV_SECRET_ERROR = (
    "A command argument appears to contain a high-confidence secret; "
    "the value was withheld."
)
EXCEPTION_SECRET_ERROR = (
    "Input or project data contains a high-confidence secret; "
    "details were withheld."
)


def _argv_secret_candidates(raw_args: Sequence[str]) -> Iterator[str]:
    """Yield tokens plus assignment-shaped joins that a shell may have split."""
    yield from raw_args
    for index in range(len(raw_args) - 1):
        left, right = raw_args[index : index + 2]
        if left.rstrip().endswith(("=", ":")) or right.lstrip().startswith(
            ("=", ":")
        ):
            yield f"{left} {right}"
    for index in range(len(raw_args) - 2):
        first, separator, value = raw_args[index : index + 3]
        if separator.strip() in {"=", ":"}:
            yield f"{first} {separator} {value}"


def parse_args_safely(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Reject secret-bearing argv tokens before argparse can quote them in diagnostics."""
    raw_args = list(sys.argv[1:] if argv is None else argv)
    for argument in _argv_secret_candidates(raw_args):
        try:
            reject_high_confidence_secret(argument, "command argument")
        except ValueError:
            parser.error(ARGV_SECRET_ERROR)
    return parser.parse_args(raw_args)


def safe_error_text(exc: BaseException) -> str:
    """Return an exception message only when it is safe to reproduce verbatim."""
    message = str(exc)
    try:
        reject_high_confidence_secret(message, "error detail")
    except ValueError:
        return EXCEPTION_SECRET_ERROR
    return message
