from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import aes_dev_001_aggregate as dev_aggregate
import aes_sec_001_aggregate as sec_aggregate
from github_checkout import (
    GITHUB_EXTRA_HEADER_KEY,
    git_clone_environment,
    redact_git_error,
    resolve_github_token,
)


class GitHubCheckoutTests(unittest.TestCase):
    def test_anonymous_environment_disables_terminal_prompt(self) -> None:
        result = git_clone_environment(None, environ={"PATH": "/usr/bin"})

        self.assertEqual(result["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn("GIT_CONFIG_COUNT", result)

    def test_authenticated_environment_appends_scoped_header(self) -> None:
        token = "test-token-value"
        result = git_clone_environment(
            token,
            token_env_name="CUSTOM_TOKEN",
            environ={
                "CUSTOM_TOKEN": token,
                "PATH": os.environ.get("PATH", ""),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "safe.directory",
                "GIT_CONFIG_VALUE_0": "/workspace",
            },
        )

        self.assertNotIn("CUSTOM_TOKEN", result)
        self.assertEqual(result["GIT_TRACE_REDACT"], "1")
        encoded = base64.b64encode(
            f"x-access-token:{token}".encode("utf-8")
        ).decode("ascii")
        self.assertEqual(result["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(result["GIT_CONFIG_KEY_0"], "safe.directory")
        self.assertEqual(result["GIT_CONFIG_KEY_1"], GITHUB_EXTRA_HEADER_KEY)
        self.assertEqual(
            result["GIT_CONFIG_VALUE_1"],
            f"AUTHORIZATION: basic {encoded}",
        )
        self.assertEqual(result["GIT_TERMINAL_PROMPT"], "0")
        configured_header = subprocess.check_output(
            ["git", "config", "--get", GITHUB_EXTRA_HEADER_KEY],
            env=result,
            text=True,
        ).strip()
        self.assertEqual(configured_header, f"AUTHORIZATION: basic {encoded}")

    def test_required_token_has_actionable_failure(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "configure the AEMS_ECOSYSTEM_TOKEN Actions secret",
        ):
            resolve_github_token(
                "AEMS_ECOSYSTEM_TOKEN",
                required=True,
                environ={},
            )

    def test_error_redaction_removes_raw_and_encoded_token(self) -> None:
        token = "private-token"
        encoded = base64.b64encode(
            f"x-access-token:{token}".encode("utf-8")
        ).decode("ascii")
        result = redact_git_error(
            f"failure {token} header={encoded}",
            token,
        )

        self.assertNotIn(token, result)
        self.assertNotIn(encoded, result)
        self.assertEqual(result, "failure *** header=***")

    def test_both_scanners_keep_credentials_out_of_clone_arguments(self) -> None:
        token = "private-token"
        for aggregate in (dev_aggregate, sec_aggregate):
            with self.subTest(module=aggregate.__name__):
                with tempfile.TemporaryDirectory() as temporary:
                    destination = Path(temporary) / "checkout"
                    with mock.patch.dict(
                        os.environ,
                        {"AEMS_ECOSYSTEM_TOKEN": token},
                    ):
                        with mock.patch.object(
                            aggregate.subprocess,
                            "run",
                        ) as run:
                            aggregate.run_git_clone(
                                "example/private",
                                destination,
                                token,
                            )

                command = run.call_args.args[0]
                environment = run.call_args.kwargs["env"]
                self.assertEqual(
                    command[-2],
                    "https://github.com/example/private.git",
                )
                self.assertNotIn(token, " ".join(command))
                self.assertNotIn("AEMS_ECOSYSTEM_TOKEN", environment)
                self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
                self.assertEqual(environment["GIT_TRACE_REDACT"], "1")
                self.assertEqual(
                    environment["GIT_CONFIG_KEY_0"],
                    GITHUB_EXTRA_HEADER_KEY,
                )

    def test_both_scanners_redact_checkout_failures(self) -> None:
        token = "private-token"
        encoded = base64.b64encode(
            f"x-access-token:{token}".encode("utf-8")
        ).decode("ascii")
        error = subprocess.CalledProcessError(
            128,
            ["git", "clone"],
            stderr=f"fatal: {token} {encoded}",
        )

        dev_entry = dev_aggregate.RepositoryEntry(
            full_name="example/private",
            role="application-project",
            ownership="project-owned",
            expected_profile=True,
            profile_required=True,
        )
        with mock.patch.object(
            dev_aggregate,
            "run_git_clone",
            side_effect=error,
        ):
            dev_result = dev_aggregate.scan_entry(
                dev_entry,
                Path("/tmp"),
                False,
                5,
                token,
            )

        sec_entry = sec_aggregate.RepositoryEntry(
            full_name="example/private",
            role="application-project",
            ownership="project-owned",
            expected_profile=True,
        )
        with mock.patch.object(
            sec_aggregate,
            "run_git_clone",
            side_effect=error,
        ):
            sec_result = sec_aggregate.scan_entry(
                sec_entry,
                Path("/tmp"),
                False,
                False,
                token,
            )

        for result in (dev_result, sec_result):
            self.assertEqual(result.status, "checkout-failed")
            self.assertNotIn(token, result.error or "")
            self.assertNotIn(encoded, result.error or "")
            self.assertIn("***", result.error or "")

    def test_workflows_run_ecosystem_jobs_and_guard_the_secret(self) -> None:
        paths = (
            ROOT / ".github" / "workflows" / "aes-dev-001-scan.yml",
            ROOT / ".github" / "workflows" / "aes-sec-001-scan.yml",
        )
        for path in paths:
            with self.subTest(path=path.name):
                workflow = path.read_text(encoding="utf-8")
                self.assertIn(
                    "github.event_name != 'workflow_dispatch'",
                    workflow,
                )
                self.assertIn(
                    "github.event_name != 'pull_request' && "
                    "secrets.AEMS_ECOSYSTEM_TOKEN || ''",
                    workflow,
                )
                self.assertEqual(
                    workflow.count(
                        "github.event_name != 'pull_request' && "
                        "secrets.AEMS_ECOSYSTEM_TOKEN || ''"
                    ),
                    3,
                )
                self.assertIn("--require-github-token", workflow)
                self.assertIn(
                    "python3 -m unittest tests.test_ecosystem_checkout -v",
                    workflow,
                )
                self.assertIn("tests/test_ecosystem_checkout.py", workflow)
                self.assertIn("scripts/github_checkout.py", workflow)


if __name__ == "__main__":
    unittest.main()
