from __future__ import annotations

from io import StringIO
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skill_install_plus_plus.cli import main
from skill_install_plus_plus.manager import RegistryState, RepoRecord, WorkspaceRoots


class PublicSurfaceTests(unittest.TestCase):
    def test_package_exports_version(self) -> None:
        import skill_install_plus_plus

        self.assertTrue(hasattr(skill_install_plus_plus, "__version__"))
        self.assertRegex(skill_install_plus_plus.__version__, r"^\d+\.\d+\.\d+$")

    def test_pyproject_exposes_skillpp_package_and_cli(self) -> None:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        self.assertTrue(pyproject.is_file())

        pyproject_text = pyproject.read_text(encoding="utf-8")
        self.assertRegex(pyproject_text, r"(?ms)^\[project\].*?^name = \"skillpp\"$")
        self.assertRegex(
            pyproject_text,
            r"(?ms)^\[project\.scripts\].*?^skillpp = \"skill_install_plus_plus\.cli:main\"$",
        )

    def test_repository_has_open_source_basics(self) -> None:
        expected = [
            "LICENSE",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "SECURITY.md",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        ]

        missing = [path for path in expected if not (PROJECT_ROOT / path).exists()]
        self.assertEqual(missing, [])

    def test_readme_mentions_public_install_paths(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("uvx skillpp", readme)
        self.assertIn("uv tool install skillpp", readme)
        self.assertIn("pipx install skillpp", readme)

    def test_readme_has_badges_logo_and_polished_sections(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertTrue((PROJECT_ROOT / "assets" / "skillpp-mark.svg").is_file())
        self.assertTrue((PROJECT_ROOT / "assets" / "skillpp-mark-alt.svg").is_file())
        self.assertIn("img.shields.io", readme)
        self.assertIn("skillpp-mark.svg", readme)
        self.assertIn("## Table of Contents", readme)
        self.assertIn("## What Skillpp Manages", readme)
        self.assertIn("## Highlights", readme)
        self.assertIn("## Support Matrix", readme)
        self.assertIn("## Why Audit-First Matters", readme)
        self.assertIn("skillpp bootstrap --source .", readme)


class RegistryTests(unittest.TestCase):
    def test_registry_round_trip_preserves_repo_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            roots = WorkspaceRoots.for_home(Path(tmp))
            state = RegistryState(
                version=1,
                repos=[
                    RepoRecord(
                        owner="jackwener",
                        repo="OpenCLI",
                        repo_root=str(roots.repos_root / "jackwener" / "OpenCLI"),
                        skills=[{"name": "opencli-browser", "relative_path": "skills/opencli-browser"}],
                    )
                ],
            )

            roots.save_registry(state)
            reloaded = roots.load_registry()

            self.assertEqual(reloaded.version, 1)
            self.assertEqual(len(reloaded.repos), 1)
            self.assertEqual(reloaded.repos[0].owner, "jackwener")
            self.assertEqual(reloaded.repos[0].repo, "OpenCLI")
            self.assertEqual(reloaded.repos[0].skills[0]["name"], "opencli-browser")


class CliTests(unittest.TestCase):
    def test_audit_command_prints_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            custom_skill = home / ".skills" / "custom" / "local-skill"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = main(["--home", str(home), "audit"])

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Managed sources: 1", output)
            self.assertIn("missing_exposure", output)

    def test_bootstrap_command_installs_current_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "skill-install-plus-plus"
            source_root.mkdir(parents=True)
            (source_root / "SKILL.md").write_text(
                "---\nname: skill-install-plus-plus\ndescription: Use when managing skills.\n---\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = main(["--home", str(home), "bootstrap", "--source", str(source_root)])

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Managed source:", output)
            self.assertIn("Policy file:", output)
            self.assertTrue((home / ".skills" / "custom" / "skill-install-plus-plus" / "SKILL.md").is_file())


class AlignCliTests(unittest.TestCase):
    def test_align_dry_run_prints_issues_and_no_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = main(["--home", str(home), "align"])

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("missing_exposure", output)
            self.assertNotIn("Alignment actions:", output)

    def test_align_apply_prints_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = main(["--home", str(home), "align", "--apply"])

            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Alignment actions:", output)
            self.assertIn("local-skill", output)


class PluginCliTests(unittest.TestCase):
    def test_install_plugin_command_normalizes_bundle_and_exports_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "understand-anything-plugin"
            (source_root / ".claude-plugin").mkdir(parents=True)
            (source_root / "skills" / "understand").mkdir(parents=True)
            (source_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (source_root / "skills" / "understand" / "SKILL.md").write_text(
                "---\nname: understand\n---\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                exit_code = main(
                    [
                        "--home",
                        str(home),
                        "install-plugin",
                        "--publisher",
                        "understand-anything",
                        "--name",
                        "understand-anything",
                        "--source",
                        str(source_root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Installed plugin bundle:", stdout.getvalue())
            self.assertTrue(
                (home / ".skills" / "plugins" / "understand-anything" / "understand-anything" / "skills" / "understand" / "SKILL.md").is_file()
            )
            self.assertTrue((home / ".agents" / "skills" / "understand" / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / "understand" / "SKILL.md").is_file())
            self.assertTrue((home / ".copilot" / "skills" / "understand" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
