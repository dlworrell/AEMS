#!/usr/bin/env python3
"""Credential-safe GitHub checkout support for AEMS aggregate scanners."""

from __future__ import annotations

import base64
from collections.abc import Mapping
import os


DEFAULT_GITHUB_TOKEN_ENV = "AEMS_ECOSYSTEM_TOKEN"
GITHUB_EXTRA_HEADER_KEY = "http.https://github.com/.extraheader"


def resolve_github_token(
    env_name: str = DEFAULT_GITHUB_TOKEN_ENV,
    *,
    required: bool = False,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Read a GitHub token without placing it in command-line arguments."""

    name = env_name.strip()
    if not name:
        if required:
            raise ValueError("a GitHub token environment-variable name is required")
        return None

    source = os.environ if environ is None else environ
    token = source.get(name, "").strip()
    if token:
        return token
    if required:
        raise ValueError(
            f"required GitHub token environment variable {name} is not set; "
            f"configure the {name} Actions secret with read-only Contents access"
        )
    return None


def git_clone_environment(
    token: str | None,
    *,
    token_env_name: str = DEFAULT_GITHUB_TOKEN_ENV,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a non-interactive Git environment with an optional auth header."""

    result = dict(os.environ if environ is None else environ)
    result["GIT_TERMINAL_PROMPT"] = "0"
    if not token:
        return result

    result.pop(token_env_name, None)
    result["GIT_TRACE_REDACT"] = "1"
    raw_count = result.get("GIT_CONFIG_COUNT", "0")
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise ValueError("GIT_CONFIG_COUNT must be an integer") from exc
    if count < 0:
        raise ValueError("GIT_CONFIG_COUNT must not be negative")

    credential = base64.b64encode(
        f"x-access-token:{token}".encode("utf-8")
    ).decode("ascii")
    result[f"GIT_CONFIG_KEY_{count}"] = GITHUB_EXTRA_HEADER_KEY
    result[f"GIT_CONFIG_VALUE_{count}"] = (
        f"AUTHORIZATION: basic {credential}"
    )
    result["GIT_CONFIG_COUNT"] = str(count + 1)
    return result


def redact_git_error(message: str, token: str | None) -> str:
    """Remove raw and encoded credential material from Git error text."""

    if not token:
        return message
    credential = base64.b64encode(
        f"x-access-token:{token}".encode("utf-8")
    ).decode("ascii")
    return message.replace(token, "***").replace(credential, "***")
