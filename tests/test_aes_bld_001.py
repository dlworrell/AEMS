from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import aes_bld_001  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "aes_bld_001" / "positive"
APPLICATION_FIXTURE = (
    ROOT / "tests" / "fixtures" / "aes_bld_001" / "application"
)


def check_by_id(
    report: aes_bld_001.EvidenceReport, requirement: str
) -> aes_bld_001.RequirementCheck:
    matches = [
        check
        for check in report.checks
        if check.requirement == requirement
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {requirement} result, found {len(matches)}"
        )
    return matches[0]


class NativeIntegrationRegressionTests(unittest.TestCase):
    def test_pipefail_version_capture_does_not_use_head(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "aes-bld-001-distributed.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("| head -n 1", workflow)

    def test_fixture_conditionals_close_without_trailing_m4_newline(
        self,
    ) -> None:
        condition = (
            '[test "x$enable_warnings_as_errors" = "xyes"])'
        )
        for fixture in (FIXTURE, APPLICATION_FIXTURE):
            with self.subTest(fixture=fixture.name):
                configure = (fixture / "configure.ac").read_text(
                    encoding="utf-8"
                )
                self.assertIn(condition, configure)

    def test_reference_library_pins_declared_cmake_libdir(self) -> None:
        presets = json.loads(
            (FIXTURE / "CMakePresets.json").read_text(encoding="utf-8")
        )
        configure_presets = presets["configurePresets"]

        self.assertGreater(len(configure_presets), 0)
        for preset in configure_presets:
            with self.subTest(preset=preset["name"]):
                self.assertEqual(
                    preset["cacheVariables"]["CMAKE_INSTALL_LIBDIR"],
                    "lib",
                )


class StructureValidationTests(unittest.TestCase):
    def test_aems_pre_adoption_profile_is_traceable(self) -> None:
        report = aes_bld_001.validate_structure(ROOT)

        self.assertTrue(report.passes)
        self.assertEqual(report.repository, "dlworrell/AEMS")
        self.assertEqual(
            report.to_dict()["summary"]["not-applicable"],
            29,
        )

    def test_reference_fixture_satisfies_every_requirement(self) -> None:
        report = aes_bld_001.validate_structure(FIXTURE)

        self.assertTrue(report.passes)
        self.assertEqual(len(report.checks), 31)
        self.assertEqual(report.to_dict()["summary"]["failed"], 0)
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R022").status,
            "passed",
        )

    def test_reference_application_satisfies_applicable_requirements(
        self,
    ) -> None:
        report = aes_bld_001.validate_structure(APPLICATION_FIXTURE)

        self.assertTrue(report.passes)
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R044").status,
            "not-applicable",
        )
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R045").status,
            "not-applicable",
        )

    def test_missing_cmake_presets_fails_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, root)
            (root / "CMakePresets.json").unlink()

            report = aes_bld_001.validate_structure(root)

        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R021").status,
            "failed",
        )

    def test_source_drift_between_frontends_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, root)
            makefile = root / "Makefile.am"
            makefile.write_text(
                makefile.read_text(encoding="utf-8").replace(
                    "src/fixture.c",
                    "src/frontend_only.c",
                    1,
                ),
                encoding="utf-8",
            )

            report = aes_bld_001.validate_structure(root)

        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R040").status,
            "failed",
        )

    def test_test_inventory_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, root)
            makefile = root / "Makefile.am"
            makefile.write_text(
                makefile.read_text(encoding="utf-8").replace(
                    "tests/test_fixture.c",
                    "tests/frontend_only_test.c",
                    1,
                ),
                encoding="utf-8",
            )

            report = aes_bld_001.validate_structure(root)

        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R042").status,
            "failed",
        )

    def test_empty_normative_test_inventory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, root)
            profile_path = root / ".aems" / "aes-bld-001.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["build"]["normative_tests"] = []
            profile_path.write_text(
                json.dumps(profile),
                encoding="utf-8",
            )

            report = aes_bld_001.validate_structure(root)

        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R022").status,
            "failed",
        )
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R034").status,
            "failed",
        )
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R042").status,
            "failed",
        )

    def test_required_tool_absence_is_a_strict_failure(self) -> None:
        def selected_which(name: str) -> str | None:
            if name == "clang-tidy":
                return None
            return f"/usr/bin/{name}"

        completed = mock.Mock(
            returncode=0,
            stdout="tool version 1.0\n",
            stderr="",
        )
        with (
            mock.patch.object(
                aes_bld_001.shutil,
                "which",
                side_effect=selected_which,
            ),
            mock.patch.object(
                aes_bld_001.subprocess,
                "run",
                return_value=completed,
            ),
        ):
            report = aes_bld_001.validate_structure(
                FIXTURE,
                require_tools=True,
            )

        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R011").status,
            "failed",
        )
        self.assertEqual(
            report.tools["clang-tidy"]["status"],
            "missing",
        )

    def test_planned_native_profile_is_traceable_without_false_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_dir = root / ".aems"
            document = root / "docs" / "engineering"
            profile_dir.mkdir()
            document.mkdir(parents=True)
            (document / "AES-BLD-001-toolchain-profile.md").write_text(
                "# Planned native build profile\n",
                encoding="utf-8",
            )
            profile = {
                "schema_version": "1.0.0",
                "standard": "AES-BLD-001",
                "repository": "dlworrell/planned",
                "applicability": "planned-native",
                "profile_document": (
                    "docs/engineering/AES-BLD-001-toolchain-profile.md"
                ),
                "waiver_log": ".aems/aes-bld-001-waivers.json",
                "authority": {
                    "repository": "dlworrell/AES",
                    "requirement_source": (
                        "standards/AES-BLD-001-native-build-toolchain-and-"
                        "distribution-parity.md"
                    ),
                },
            }
            (profile_dir / "aes-bld-001.json").write_text(
                json.dumps(profile),
                encoding="utf-8",
            )
            (profile_dir / "aes-bld-001-waivers.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "standard": "AES-BLD-001",
                        "repository": "dlworrell/planned",
                        "waivers": [],
                    }
                ),
                encoding="utf-8",
            )

            report = aes_bld_001.validate_structure(root)

        self.assertTrue(report.passes)
        self.assertEqual(
            report.to_dict()["summary"]["not-applicable"],
            29,
        )

    def test_expired_waiver_fails_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, root)
            waiver_path = (
                root / ".aems" / "aes-bld-001-waivers.json"
            )
            waiver_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "standard": "AES-BLD-001",
                        "repository": "aems/reference-c-library",
                        "waivers": [
                            {
                                "requirement": "AES-BLD-001-R025",
                                "rationale": "Target lacks sanitizer support.",
                                "owner": "owner",
                                "reviewer": "reviewer",
                                "compensating_validation": (
                                    "Run host tests and static analysis."
                                ),
                                "expires_on": "2000-01-01",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = aes_bld_001.validate_structure(root)

        check = check_by_id(report, "AES-BLD-001-R051")
        self.assertEqual(check.status, "failed")
        self.assertIn("expired", check.message)


class InstallParityTests(unittest.TestCase):
    def make_stages(
        self, temporary: str
    ) -> tuple[Path, Path, Path]:
        base = Path(temporary)
        cmake = base / "cmake"
        autotools = base / "autotools"
        for stage in (cmake, autotools):
            (stage / "include" / "aes_fixture").mkdir(parents=True)
            (stage / "lib" / "pkgconfig").mkdir(parents=True)
            (stage / "include" / "aes_fixture" / "fixture.h").write_text(
                "int aes_fixture_add(int left, int right);\n",
                encoding="utf-8",
            )
            (stage / "lib" / "pkgconfig" / "aes-fixture.pc").write_text(
                "Name: aes-fixture\nVersion: 1.0.0\n",
                encoding="utf-8",
            )
            (stage / "lib" / "libaes_fixture.a").write_bytes(
                b"not-an-archive"
            )
        return cmake, autotools, FIXTURE / ".aems" / "aes-bld-001.json"

    def test_equivalent_staged_installs_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cmake, autotools, profile = self.make_stages(temporary)
            with (
                mock.patch.object(
                    aes_bld_001.shutil,
                    "which",
                    return_value="/usr/bin/nm",
                ),
                mock.patch.object(
                    aes_bld_001,
                    "_symbols",
                    return_value={"aes_fixture_add"},
                ),
            ):
                report = aes_bld_001.compare_installs(
                    cmake,
                    autotools,
                    profile_path=profile,
                )

        self.assertTrue(report.passes)
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R043").status,
            "passed",
        )
        self.assertEqual(
            check_by_id(report, "AES-BLD-001-R044").status,
            "passed",
        )

    def test_extra_installed_file_fails_manifest_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cmake, autotools, profile = self.make_stages(temporary)
            (cmake / "include" / "cmake-only.h").write_text(
                "/* drift */\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    aes_bld_001.shutil,
                    "which",
                    return_value="/usr/bin/nm",
                ),
                mock.patch.object(
                    aes_bld_001,
                    "_symbols",
                    return_value={"aes_fixture_add"},
                ),
            ):
                report = aes_bld_001.compare_installs(
                    cmake,
                    autotools,
                    profile_path=profile,
                )

        check = check_by_id(report, "AES-BLD-001-R043")
        self.assertEqual(check.status, "failed")
        self.assertIn("cmake-only: include/cmake-only.h", check.evidence)

    def test_installed_header_content_drift_fails_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cmake, autotools, profile = self.make_stages(temporary)
            (
                autotools / "include" / "aes_fixture" / "fixture.h"
            ).write_text(
                "int different_api(void);\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    aes_bld_001.shutil,
                    "which",
                    return_value="/usr/bin/nm",
                ),
                mock.patch.object(
                    aes_bld_001,
                    "_symbols",
                    return_value={"aes_fixture_add"},
                ),
            ):
                report = aes_bld_001.compare_installs(
                    cmake,
                    autotools,
                    profile_path=profile,
                )

        check = check_by_id(report, "AES-BLD-001-R043")
        self.assertEqual(check.status, "failed")
        self.assertIn(
            "content-mismatch: include/aes_fixture/fixture.h",
            check.evidence,
        )

    def test_package_metadata_drift_fails_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cmake, autotools, profile = self.make_stages(temporary)
            (
                autotools / "lib" / "pkgconfig" / "aes-fixture.pc"
            ).write_text(
                "Name: aes-fixture\nVersion: 2.0.0\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    aes_bld_001.shutil,
                    "which",
                    return_value="/usr/bin/nm",
                ),
                mock.patch.object(
                    aes_bld_001,
                    "_symbols",
                    return_value={"aes_fixture_add"},
                ),
            ):
                report = aes_bld_001.compare_installs(
                    cmake,
                    autotools,
                    profile_path=profile,
                )

        check = check_by_id(report, "AES-BLD-001-R043")
        self.assertEqual(check.status, "failed")
        self.assertIn(
            "content-mismatch: lib/pkgconfig/aes-fixture.pc",
            check.evidence,
        )

    def test_public_symbol_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cmake, autotools, profile = self.make_stages(temporary)
            with (
                mock.patch.object(
                    aes_bld_001.shutil,
                    "which",
                    return_value="/usr/bin/nm",
                ),
                mock.patch.object(
                    aes_bld_001,
                    "_symbols",
                    side_effect=[
                        {"aes_fixture_add"},
                        {"aes_fixture_subtract"},
                    ],
                ),
            ):
                report = aes_bld_001.compare_installs(
                    cmake,
                    autotools,
                    profile_path=profile,
                )

        check = check_by_id(report, "AES-BLD-001-R044")
        self.assertEqual(check.status, "failed")
        self.assertIn("cmake-only=['aes_fixture_add']", check.evidence[0])
        self.assertIn(
            "autotools-only=['aes_fixture_subtract']",
            check.evidence[0],
        )


class EvidenceSchemaTests(unittest.TestCase):
    def test_generated_report_matches_machine_readable_contract(self) -> None:
        report = aes_bld_001.validate_structure(FIXTURE)
        value = report.to_dict()
        schema = json.loads(
            (
                ROOT
                / "schemas"
                / "aes-bld-001-evidence-v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(aes_bld_001.evidence_errors(value), [])
        self.assertEqual(
            set(schema["required"]),
            set(value),
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            value["schema_version"],
        )

    def test_malformed_evidence_is_rejected(self) -> None:
        value = aes_bld_001.validate_structure(FIXTURE).to_dict()
        value["checks"][0].pop("status")
        value["summary"]["passed"] = 99

        errors = aes_bld_001.evidence_errors(value)

        self.assertTrue(
            any("checks[0].status" in error for error in errors)
        )
        self.assertTrue(
            any("summary.passed" in error for error in errors)
        )


class RepositoryInventoryTests(unittest.TestCase):
    def test_inventory_covers_every_project_owned_future_c_repository(self) -> None:
        inventory = json.loads(
            (
                ROOT / "config" / "aes-bld-001-repositories.json"
            ).read_text(encoding="utf-8")
        )
        entries = inventory["repositories"]
        names = [entry["full_name"] for entry in entries]
        project_owned = {
            entry["full_name"]
            for entry in entries
            if entry["ownership"] == "project-owned"
        }

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            project_owned,
            {
                "dlworrell/AEMS",
                "dlworrell/P0",
                "dlworrell/repo_templates",
                "dlworrell/Catylist",
                "dlworrell/AES",
                "dlworrell/atarix",
                "dlworrell/code-noodling",
                "dlworrell/audiblebooks",
                "dlworrell/engineering-docs-toolkit",
                "dlworrell/EWT",
                "dlworrell/herkules-1934-english",
                "dlworrell/JAG",
                "dlworrell/evo",
                "dlworrell/Just-a-Geek-LLC",
                "dlworrell/Rocket_demo",
                "dlworrell/MayaUSD2017Bridge",
            },
        )
        self.assertTrue(
            all(
                entry["applicability"]
                in {"active-native", "planned-native"}
                and entry["profile_required"] is True
                for entry in entries
                if entry["ownership"] == "project-owned"
            )
        )
        self.assertTrue(
            all(
                entry["enforcement_state"] == "excluded"
                and entry["profile_required"] is False
                for entry in entries
                if entry["ownership"] != "project-owned"
            )
        )


if __name__ == "__main__":
    unittest.main()
