#!/usr/bin/env python3
"""Check AES CodeQL evidence from the real-header fixture.

tests/fixtures/codeql/cpp-real-headers/real.c is extracted with the real
system headers, once plain and once with _FORTIFY_SOURCE. Each evidence JSON
written by scripts/aes_codeql.py must contain every expected AES finding, so
a header or fortification change that hides a call fails CI instead of
silently dropping coverage.

Usage: check_real_header_evidence.py LABEL=EVIDENCE.json [LABEL=EVIDENCE.json ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BANNED_RULE = "aes/cpp/banned-interface"
BANNED_INTERFACES = ("strcpy", "strcat", "sprintf", "vsprintf", "system", "popen", "atoi")
REQUIRED_RULES = ("aes/cpp/candidate-secret-memset", "aes/cpp/discarded-snprintf-result")
# BannedInterfaces reports the canonical interface name, even for fortified forms.
BANNED_MESSAGE = re.compile(r"^AES-SEC-001: (\w+) is banned\b")


def missing_findings(evidence: dict) -> list[str]:
    """Return the expected findings that the evidence does not contain."""
    findings = evidence["analysis"]["findings"]
    banned = set()
    rules = set()
    for finding in findings:
        rules.add(finding["rule_id"])
        if finding["rule_id"] == BANNED_RULE:
            match = BANNED_MESSAGE.match(finding["message"])
            if match:
                banned.add(match.group(1))
    missing = [f"{BANNED_RULE} ({name})" for name in BANNED_INTERFACES if name not in banned]
    missing += [rule for rule in REQUIRED_RULES if rule not in rules]
    return missing


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    failed = False
    for argument in argv:
        label, separator, path = argument.partition("=")
        if not separator or not label or not path:
            print(f"error: expected LABEL=PATH, got {argument!r}", file=sys.stderr)
            return 2
        evidence = json.loads(Path(path).read_text(encoding="utf-8"))
        missing = missing_findings(evidence)
        count = evidence["analysis"].get("finding_count", len(evidence["analysis"]["findings"]))
        if missing:
            failed = True
            print(f"FAIL {label}: {count} findings; missing: {', '.join(missing)}")
        else:
            print(f"OK   {label}: {count} findings; all {len(BANNED_INTERFACES)} banned "
                  f"interfaces and {len(REQUIRED_RULES)} review rules present")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
