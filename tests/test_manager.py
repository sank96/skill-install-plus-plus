from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skill_install_plus_plus.manager import PluginRecord, WorkspaceRoots, _create_directory_link


class WorkspaceRootsTests(unittest.TestCase):
    def test_for_home_uses_skills_tree_and_client_roots(self) -> None:
        home = Path("C:/Users/example")

        roots = WorkspaceRoots.for_home(home)

        self.assertEqual(roots.skills_root, home / ".skills")
        self.assertEqual(roots.repos_root, home / ".skills" / "repos")
        self.assertEqual(roots.custom_root, home / ".skills" / "custom")
        self.assertEqual(roots.plugins_root, home / ".skills" / "plugins")
        self.assertEqual(roots.registry_path, home / ".skills" / "registry.json")
        self.assertEqual(roots.codex_root, home / ".agents" / "skills")
        self.assertEqual(roots.claude_root, home / ".claude" / "skills")
        self.assertEqual(roots.copilot_root, home / ".copilot" / "skills")


class DiscoveryTests(unittest.TestCase):
    def test_discover_sources_finds_custom_and_repo_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            custom_skill = home / ".skills" / "custom" / "local-skill"
            repo_skill = home / ".skills" / "repos" / "acme" / "toolbox" / "skills" / "repo-skill"
            custom_skill.mkdir(parents=True)
            repo_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")
            (repo_skill / "SKILL.md").write_text("---\nname: repo-skill\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            discovered = roots.discover_sources()

            self.assertEqual({item.name for item in discovered}, {"local-skill", "repo-skill"})
            repo_source = next(item for item in discovered if item.name == "repo-skill")
            self.assertEqual(repo_source.owner, "acme")
            self.assertEqual(repo_source.repo, "toolbox")


class PluginDiscoveryTests(unittest.TestCase):
    def test_discover_plugin_bundles_finds_managed_plugins_and_hybrid_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            hybrid_repo = home / ".skills" / "repos" / "obra" / "superpowers"
            (plugin_bundle / ".claude-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "plugin-skill").mkdir(parents=True)
            (hybrid_repo / ".claude-plugin").mkdir(parents=True)
            (hybrid_repo / "skills" / "brainstorming").mkdir(parents=True)
            (plugin_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin_bundle / "skills" / "plugin-skill" / "SKILL.md").write_text(
                "---\nname: plugin-skill\n---\n",
                encoding="utf-8",
            )
            (hybrid_repo / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (hybrid_repo / "skills" / "brainstorming" / "SKILL.md").write_text(
                "---\nname: brainstorming\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            bundles = roots.discover_plugin_bundles()

            self.assertEqual({bundle.name for bundle in bundles}, {"suite", "superpowers"})
            managed = next(bundle for bundle in bundles if bundle.name == "suite")
            hybrid = next(bundle for bundle in bundles if bundle.name == "superpowers")
            self.assertEqual(managed.bundle_type, "plugin-managed")
            self.assertEqual(managed.manifest_type, "claude")
            self.assertEqual(managed.exported_skills, ["plugin-skill"])
            self.assertEqual(hybrid.bundle_type, "hybrid")
            self.assertEqual(hybrid.exported_skills, ["brainstorming"])

    def test_discover_plugin_bundles_supports_single_level_legacy_repo_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hybrid_repo = home / ".skills" / "repos" / "superpowers"
            (hybrid_repo / ".claude-plugin").mkdir(parents=True)
            (hybrid_repo / "skills" / "brainstorming").mkdir(parents=True)
            (hybrid_repo / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (hybrid_repo / "skills" / "brainstorming" / "SKILL.md").write_text(
                "---\nname: brainstorming\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            bundles = roots.discover_plugin_bundles()

            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].name, "superpowers")
            self.assertEqual(bundles[0].bundle_type, "hybrid")
            self.assertEqual(bundles[0].exported_skills, ["brainstorming"])


class AuditTests(unittest.TestCase):
    def test_audit_reports_missing_client_exposures_for_managed_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            missing = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("local-skill", "codex", "missing_exposure"), missing)
            self.assertIn(("local-skill", "claude", "missing_exposure"), missing)
            self.assertIn(("local-skill", "copilot", "missing_exposure"), missing)

    def test_audit_flags_legacy_copies_inside_client_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            claude_copy = home / ".claude" / "skills" / "local-skill"
            skill_dir.mkdir(parents=True)
            claude_copy.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")
            (claude_copy / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            legacy = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("local-skill", "claude", "legacy_copy"), legacy)


class PluginAuditTests(unittest.TestCase):
    def test_audit_reports_missing_plugin_injections_and_manual_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            (plugin_bundle / ".claude-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "plugin-skill").mkdir(parents=True)
            (plugin_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin_bundle / "skills" / "plugin-skill" / "SKILL.md").write_text(
                "---\nname: plugin-skill\n---\n",
                encoding="utf-8",
            )

            manual_bundle = home / ".codex" / "understand-anything" / "understand-anything-plugin"
            (manual_bundle / ".claude-plugin").mkdir(parents=True)
            (manual_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            plugin_missing = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("plugin-skill", "codex", "missing_plugin_injection"), plugin_missing)
            self.assertIn(("plugin-skill", "claude", "missing_plugin_injection"), plugin_missing)
            self.assertIn(("plugin-skill", "copilot", "missing_plugin_injection"), plugin_missing)
            self.assertIn(("understand-anything-plugin", "codex", "manual_bundle_detected"), plugin_missing)
            self.assertEqual(report.classification_counts["plugin-managed"], 1)
            self.assertEqual(report.classification_counts["manual"], 1)

    def test_align_apply_creates_exported_plugin_skill_exposures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            (plugin_bundle / ".claude-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "plugin-skill").mkdir(parents=True)
            (plugin_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin_bundle / "skills" / "plugin-skill" / "SKILL.md").write_text(
                "---\nname: plugin-skill\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            report, actions = roots.align(apply=True)

            self.assertFalse(report.issues)
            self.assertTrue(any("plugin-skill" in action for action in actions))
            self.assertTrue((home / ".agents" / "skills" / "plugin-skill" / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / "plugin-skill" / "SKILL.md").is_file())
            self.assertTrue((home / ".copilot" / "skills" / "plugin-skill" / "SKILL.md").is_file())

    def test_audit_deduplicates_wrapper_and_nested_manual_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            wrapper_bundle = home / ".codex" / "understand-anything"
            payload_bundle = wrapper_bundle / "understand-anything-plugin"
            (wrapper_bundle / ".claude-plugin").mkdir(parents=True)
            (payload_bundle / ".claude-plugin").mkdir(parents=True)
            (payload_bundle / "skills" / "understand").mkdir(parents=True)
            (wrapper_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (payload_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (payload_bundle / "skills" / "understand" / "SKILL.md").write_text(
                "---\nname: understand\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            manual_entries = [(issue.skill_name, issue.path) for issue in report.issues if issue.code == "manual_bundle_detected"]
            self.assertEqual(len(manual_entries), 1)
            self.assertEqual(manual_entries[0][0], "understand-anything-plugin")
            self.assertEqual(report.classification_counts["manual"], 1)

    def test_audit_ignores_backup_like_manual_bundle_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            backup_bundle = home / ".codex" / "superpowers.backup-20260324160819"
            (backup_bundle / ".claude-plugin").mkdir(parents=True)
            (backup_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            self.assertFalse([issue for issue in report.issues if issue.code == "manual_bundle_detected"])


class PluginRegistryTests(unittest.TestCase):
    def test_registry_round_trip_preserves_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            roots.registry_path.parent.mkdir(parents=True, exist_ok=True)
            roots.registry_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "repos": [],
                        "plugins": [
                            {
                                "publisher": "acme",
                                "name": "suite",
                                "bundle_root": str(home / ".skills" / "plugins" / "acme" / "suite"),
                                "manifest_type": "claude",
                                "exported_skills": ["plugin-skill"],
                                "clients": {"codex": "exported-skills"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            reloaded = roots.load_registry()

            self.assertEqual(reloaded.version, 2)
            self.assertEqual(len(reloaded.plugins), 1)
            self.assertEqual(reloaded.plugins[0].name, "suite")
            self.assertEqual(reloaded.plugins[0].exported_skills, ["plugin-skill"])


class PluginUpdateTests(unittest.TestCase):
    def test_update_repos_includes_git_backed_plugin_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            plugin_bundle.mkdir(parents=True)
            (plugin_bundle / ".git").mkdir()
            roots.save_registry(
                roots.load_registry().__class__(
                    version=2,
                    repos=[],
                    plugins=[
                        PluginRecord(
                            publisher="acme",
                            name="suite",
                            bundle_root=str(plugin_bundle),
                            manifest_type="claude",
                            exported_skills=[],
                            clients={},
                        ),
                    ],
                )
            )

            with mock.patch("skill_install_plus_plus.manager._run_git", return_value="Already up to date.") as run_git:
                results = roots.update_repos()

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].success)
            run_git.assert_called_once()


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_self_creates_source_links_exposures_and_policy_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "skill-install-plus-plus"
            source_root.mkdir(parents=True)
            (source_root / "SKILL.md").write_text(
                "---\nname: skill-install-plus-plus\ndescription: Use when managing skills.\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            result = roots.bootstrap_self(source_root)

            managed_source = home / ".skills" / "custom" / "skill-install-plus-plus"
            self.assertTrue((managed_source / "SKILL.md").is_file())
            self.assertTrue((home / ".agents" / "skills" / "skill-install-plus-plus" / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / "skill-install-plus-plus" / "SKILL.md").is_file())
            self.assertTrue((home / ".copilot" / "skills" / "skill-install-plus-plus" / "SKILL.md").is_file())

            self.assertTrue(any(path == managed_source for path in result.created_paths))

            codex_policy = (home / ".codex" / "AGENTS.override.md").read_text(encoding="utf-8")
            claude_policy = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            copilot_policy = (home / ".copilot" / "copilot-instructions.md").read_text(encoding="utf-8")

            self.assertIn("skill-install-plus-plus", codex_policy)
            self.assertIn("skill-install-plus-plus", claude_policy)
            self.assertIn("skill-install-plus-plus", copilot_policy)

    def test_bootstrap_self_reuses_codex_custom_aggregate_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "skill-install-plus-plus"
            source_root.mkdir(parents=True)
            (source_root / "SKILL.md").write_text(
                "---\nname: skill-install-plus-plus\ndescription: Use when managing skills.\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)
            roots.ensure_root_directories()
            _create_directory_link(roots.codex_root / "custom", roots.custom_root)

            first = roots.bootstrap_self(source_root)
            second = roots.bootstrap_self(source_root)

            self.assertFalse((roots.codex_root / "skill-install-plus-plus").exists())
            self.assertTrue((roots.codex_root / "custom" / "skill-install-plus-plus" / "SKILL.md").is_file())
            self.assertTrue(any("existing codex custom aggregate" in item.lower() for item in first.skipped_paths))
            self.assertTrue(any("already present" in item.lower() for item in second.skipped_paths))

            codex_policy = (home / ".codex" / "AGENTS.override.md").read_text(encoding="utf-8")
            self.assertEqual(codex_policy.count("skill-install-plus-plus"), 1)


class RepoInstallTests(unittest.TestCase):
    def test_install_repo_skills_uses_safe_exposure_name_for_windows_unsafe_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            repo_root = home / ".skills" / "repos" / "nextlevelbuilder" / "ui-ux-pro-max-skill"
            skill_dir = repo_root / ".claude" / "skills" / "banner-design"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: ckm:banner-design\n---\n",
                encoding="utf-8",
            )

            result = roots.install_repo_skills(
                repo_slug="nextlevelbuilder/ui-ux-pro-max-skill",
                skill_paths=[".claude/skills/banner-design"],
            )

            self.assertEqual(result.installed[0].name, "ckm:banner-design")
            self.assertTrue((home / ".agents" / "skills" / "banner-design" / "SKILL.md").is_file())
            self.assertTrue((home / ".claude" / "skills" / "banner-design" / "SKILL.md").is_file())
            self.assertTrue((home / ".copilot" / "skills" / "banner-design" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
