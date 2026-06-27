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

    def test_discover_sources_groups_provider_specific_repo_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "pbakaus" / "impeccable"
            (repo_root / ".git").mkdir(parents=True)
            for relative in [
                ".agents/skills/harden",
                ".claude/skills/harden",
                ".codex/skills/harden",
                ".cursor/skills/harden",
                ".github/skills/harden",
                "source/skills/harden",
            ]:
                skill_dir = repo_root / relative
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: harden\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            discovered = roots.discover_sources()

            self.assertEqual([item.name for item in discovered], ["harden"])
            source = discovered[0]
            self.assertEqual(set(source.client_paths), {"codex", "claude", "copilot"})
            self.assertEqual(source.client_paths["codex"], repo_root / ".codex" / "skills" / "harden")
            self.assertEqual(source.client_paths["claude"], repo_root / ".claude" / "skills" / "harden")
            self.assertEqual(source.client_paths["copilot"], repo_root / ".github" / "skills" / "harden")
            self.assertEqual(source.path, repo_root / ".codex" / "skills" / "harden")

    def test_discover_sources_groups_plugin_provider_specific_repo_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "upstash" / "context7"
            (repo_root / ".git").mkdir(parents=True)
            for relative in [
                "skills/context7-mcp",
                "plugins/claude/context7/skills/context7-mcp",
                "plugins/codex/context7/skills/context7-mcp",
                "plugins/copilot/context7/skills/context7-mcp",
                "plugins/cursor/context7/skills/context7-mcp",
                "packages/pi/skills/context7-docs",
            ]:
                skill_dir = repo_root / relative
                skill_dir.mkdir(parents=True)
                skill_name = "context7-docs" if "context7-docs" in relative else "context7-mcp"
                (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_name}\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            discovered = roots.discover_sources()

            self.assertEqual([item.name for item in discovered], ["context7-mcp"])
            source = discovered[0]
            self.assertEqual(set(source.client_paths), {"codex", "claude", "copilot"})
            self.assertEqual(source.client_paths["codex"], repo_root / "plugins" / "codex" / "context7" / "skills" / "context7-mcp")
            self.assertEqual(source.client_paths["claude"], repo_root / "plugins" / "claude" / "context7" / "skills" / "context7-mcp")
            self.assertEqual(source.client_paths["copilot"], repo_root / "plugins" / "copilot" / "context7" / "skills" / "context7-mcp")


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

    def test_audit_reports_invalid_skill_name_for_all_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "banner-design"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: ckm:banner-design\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            invalid = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("ckm:banner-design", "codex", "invalid_skill_name"), invalid)
            self.assertIn(("ckm:banner-design", "claude", "invalid_skill_name"), invalid)
            self.assertIn(("ckm:banner-design", "copilot", "invalid_skill_name"), invalid)

    def test_audit_reports_invalid_skill_frontmatter_for_all_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "harden"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: harden\n"
                "description: Make interfaces production-ready: error handling\n"
                "---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            invalid = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("harden", "codex", "invalid_skill_frontmatter"), invalid)
            self.assertIn(("harden", "claude", "invalid_skill_frontmatter"), invalid)
            self.assertIn(("harden", "copilot", "invalid_skill_frontmatter"), invalid)
            self.assertTrue(any("invalid YAML" in issue.message for issue in report.issues if issue.skill_name == "harden"))

    def test_audit_uses_provider_specific_repo_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "pbakaus" / "impeccable"
            (repo_root / ".git").mkdir(parents=True)
            codex_skill = repo_root / ".codex" / "skills" / "harden"
            claude_skill = repo_root / ".claude" / "skills" / "harden"
            ignored_skill = repo_root / ".cursor" / "skills" / "harden"
            for skill_dir in [codex_skill, claude_skill, ignored_skill]:
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: harden\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)
            _create_directory_link(home / ".agents" / "skills" / "harden", codex_skill)
            _create_directory_link(home / ".claude" / "skills" / "harden", claude_skill)

            report = roots.audit()

            self.assertEqual([source.name for source in report.sources], ["harden"])
            harden_issues = [issue for issue in report.issues if issue.skill_name == "harden"]
            self.assertEqual(harden_issues, [])

    def test_audit_uses_generic_repo_skill_as_missing_provider_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "nextlevelbuilder" / "ui-ux-pro-max-skill"
            generic_skill = repo_root / "cli" / "assets" / "skills" / "design"
            claude_skill = repo_root / ".claude" / "skills" / "design"
            for skill_dir in [generic_skill, claude_skill]:
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: design\n---\n", encoding="utf-8")
            (repo_root / ".git").mkdir()

            roots = WorkspaceRoots.for_home(home)
            _create_directory_link(home / ".agents" / "skills" / "design", generic_skill)
            _create_directory_link(home / ".claude" / "skills" / "design", claude_skill)
            _create_directory_link(home / ".copilot" / "skills" / "design", generic_skill)

            report = roots.audit()

            self.assertEqual([source.name for source in report.sources], ["design"])
            source = report.sources[0]
            self.assertEqual(source.client_paths["codex"], generic_skill)
            self.assertEqual(source.client_paths["claude"], claude_skill)
            self.assertEqual(source.client_paths["copilot"], generic_skill)
            design_issues = [issue for issue in report.issues if issue.skill_name == "design"]
            self.assertEqual(design_issues, [])

    def test_audit_uses_primary_repo_skill_as_declared_client_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "nextlevelbuilder" / "ui-ux-pro-max-skill"
            primary_skill = repo_root / ".claude" / "skills" / "ui-ux-pro-max"
            primary_skill.mkdir(parents=True)
            (repo_root / ".git").mkdir()
            (repo_root / "skill.json").write_text(
                '{"name":"ui-ux-pro-max","platforms":["claude","codex","copilot"]}',
                encoding="utf-8",
            )
            (primary_skill / "SKILL.md").write_text("---\nname: ui-ux-pro-max\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)
            _create_directory_link(home / ".agents" / "skills" / "ui-ux-pro-max", primary_skill)
            _create_directory_link(home / ".claude" / "skills" / "ui-ux-pro-max", primary_skill)
            _create_directory_link(home / ".copilot" / "skills" / "ui-ux-pro-max", primary_skill)

            report = roots.audit()

            self.assertEqual([source.name for source in report.sources], ["ui-ux-pro-max"])
            source = report.sources[0]
            self.assertEqual(source.client_paths["codex"], primary_skill)
            self.assertEqual(source.client_paths["claude"], primary_skill)
            self.assertEqual(source.client_paths["copilot"], primary_skill)
            primary_issues = [issue for issue in report.issues if issue.skill_name == "ui-ux-pro-max"]
            self.assertEqual(primary_issues, [])

    def test_audit_reports_stale_managed_client_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "pbakaus" / "impeccable"
            current_skill = repo_root / ".agents" / "skills" / "impeccable"
            old_skill = repo_root / ".codex" / "skills" / "harden"
            current_skill.mkdir(parents=True)
            old_skill.mkdir(parents=True)
            (repo_root / ".git").mkdir()
            (current_skill / "SKILL.md").write_text("---\nname: impeccable\n---\n", encoding="utf-8")
            (old_skill / "SKILL.md").write_text("---\nname: harden\n---\n", encoding="utf-8")
            _create_directory_link(home / ".agents" / "skills" / "harden", old_skill)
            (old_skill / "SKILL.md").unlink()
            old_skill.rmdir()

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            stale = [
                issue
                for issue in report.issues
                if issue.skill_name == "harden" and issue.client == "codex" and issue.code == "stale_managed_exposure"
            ]
            self.assertEqual(len(stale), 1)


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

    def test_audit_skips_plugin_injections_for_native_installed_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "sprint-reply" / "sprint-tool"
            (plugin_bundle / ".codex-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "sprint-tool-reviewer").mkdir(parents=True)
            (plugin_bundle / ".codex-plugin" / "plugin.json").write_text('{"name":"sprint-tool"}', encoding="utf-8")
            (plugin_bundle / "skills" / "sprint-tool-reviewer" / "SKILL.md").write_text(
                "---\nname: sprint-tool-reviewer\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            with mock.patch("skill_install_plus_plus.manager.shutil.which", return_value="plugin-cli"), mock.patch.object(
                WorkspaceRoots,
                "_native_plugin_installed",
                side_effect=lambda client, plugin_name, marketplace_name, cli_path=None: (
                    client in {"codex", "claude"} and marketplace_name == "sprint-tool-skills"
                ),
            ):
                report = roots.audit()

            plugin_missing = {
                (issue.skill_name, issue.client, issue.code)
                for issue in report.issues
                if issue.skill_name == "sprint-tool-reviewer"
            }
            self.assertNotIn(("sprint-tool-reviewer", "codex", "missing_plugin_injection"), plugin_missing)
            self.assertNotIn(("sprint-tool-reviewer", "claude", "missing_plugin_injection"), plugin_missing)
            self.assertIn(("sprint-tool-reviewer", "copilot", "missing_plugin_injection"), plugin_missing)

    def test_native_plugin_installed_uses_cached_plugin_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            roots = WorkspaceRoots.for_home(Path(tmp))
            output = json.dumps(
                {
                    "installed": [
                        {
                            "pluginId": "sprint-tool@sprint-tool-skills",
                            "name": "sprint-tool",
                            "marketplaceName": "sprint-tool-skills",
                        }
                    ]
                }
            )

            with mock.patch("skill_install_plus_plus.manager._run_captured", return_value=(True, output)) as run:
                self.assertTrue(
                    roots._native_plugin_installed(
                        "codex",
                        "sprint-tool",
                        "sprint-tool-skills",
                        cli_path="plugin-cli",
                    )
                )
                self.assertTrue(
                    roots._native_plugin_installed(
                        "codex",
                        "sprint-tool",
                        "sprint-tool-skills",
                        cli_path="plugin-cli",
                    )
                )

            run.assert_called_once_with(["plugin-cli", "plugin", "list", "--json"], timeout=30)

    def test_audit_does_not_double_inject_hybrid_plugin_skill_when_provider_output_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "pbakaus" / "impeccable"
            agents_skill = repo_root / ".agents" / "skills" / "impeccable"
            claude_skill = repo_root / ".claude" / "skills" / "impeccable"
            copilot_skill = repo_root / ".github" / "skills" / "impeccable"
            plugin_skill = repo_root / "plugin" / "skills" / "impeccable"
            for skill_dir in [agents_skill, claude_skill, copilot_skill, plugin_skill]:
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: impeccable\n---\n", encoding="utf-8")
            (repo_root / ".claude-plugin").mkdir(parents=True)
            (repo_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (repo_root / ".git").mkdir()
            _create_directory_link(home / ".agents" / "skills" / "impeccable", agents_skill)
            _create_directory_link(home / ".claude" / "skills" / "impeccable", claude_skill)
            _create_directory_link(home / ".copilot" / "skills" / "impeccable", copilot_skill)

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            plugin_issues = [
                issue
                for issue in report.issues
                if issue.skill_name == "impeccable" and issue.code == "missing_plugin_injection"
            ]
            self.assertEqual(plugin_issues, [])

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

    def test_audit_reports_invalid_plugin_exported_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            (plugin_bundle / ".claude-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "banner-design").mkdir(parents=True)
            (plugin_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin_bundle / "skills" / "banner-design" / "SKILL.md").write_text(
                "---\nname: ckm:banner-design\n---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            invalid = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("ckm:banner-design", "codex", "invalid_skill_name"), invalid)
            self.assertIn(("ckm:banner-design", "claude", "invalid_skill_name"), invalid)
            self.assertIn(("ckm:banner-design", "copilot", "invalid_skill_name"), invalid)

    def test_audit_reports_invalid_plugin_exported_skill_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin_bundle = home / ".skills" / "plugins" / "acme" / "suite"
            (plugin_bundle / ".claude-plugin").mkdir(parents=True)
            (plugin_bundle / "skills" / "harden").mkdir(parents=True)
            (plugin_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin_bundle / "skills" / "harden" / "SKILL.md").write_text(
                "---\n"
                "name: harden\n"
                "description: Make interfaces production-ready: error handling\n"
                "---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            invalid = {(issue.skill_name, issue.client, issue.code) for issue in report.issues}
            self.assertIn(("harden", "codex", "invalid_skill_frontmatter"), invalid)
            self.assertIn(("harden", "claude", "invalid_skill_frontmatter"), invalid)
            self.assertIn(("harden", "copilot", "invalid_skill_frontmatter"), invalid)

    def test_audit_detects_manual_bundle_in_agents_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            manual_bundle = home / ".agents" / "understand-anything-plugin"
            (manual_bundle / ".claude-plugin").mkdir(parents=True)
            (manual_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            manual_entries = [
                (issue.skill_name, issue.client, issue.code)
                for issue in report.issues
                if issue.code == "manual_bundle_detected"
            ]
            self.assertIn(("understand-anything-plugin", "codex", "manual_bundle_detected"), manual_entries)

    def test_audit_detects_manual_bundle_in_claude_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            manual_bundle = home / ".claude" / "understand-anything-plugin"
            (manual_bundle / ".claude-plugin").mkdir(parents=True)
            (manual_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            manual_entries = [
                (issue.skill_name, issue.client, issue.code)
                for issue in report.issues
                if issue.code == "manual_bundle_detected"
            ]
            self.assertIn(("understand-anything-plugin", "claude", "manual_bundle_detected"), manual_entries)

    def test_audit_deduplicates_manual_bundle_when_codex_links_to_agents_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            agents_root = home / ".agents"
            manual_bundle = agents_root / "understand-anything-plugin"
            (manual_bundle / ".claude-plugin").mkdir(parents=True)
            (manual_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            _create_directory_link(home / ".codex", agents_root)

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            manual_entries = [
                (issue.skill_name, issue.client, issue.code)
                for issue in report.issues
                if issue.code == "manual_bundle_detected"
            ]
            self.assertEqual(
                manual_entries,
                [("understand-anything-plugin", "codex", "manual_bundle_detected")],
            )

    def test_audit_ignores_backup_like_manual_bundle_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            backup_bundle = home / ".codex" / "superpowers.backup-20260324160819"
            (backup_bundle / ".claude-plugin").mkdir(parents=True)
            (backup_bundle / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report = roots.audit()

            self.assertFalse([issue for issue in report.issues if issue.code == "manual_bundle_detected"])


class AlignRepairTests(unittest.TestCase):
    def test_align_apply_repairs_broken_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            gone = home / "gone"
            gone.mkdir()
            claude_entry = home / ".claude" / "skills" / "local-skill"
            _create_directory_link(claude_entry, gone)
            gone.rmdir()

            roots = WorkspaceRoots.for_home(home)

            pre = roots.audit()
            broken = [i for i in pre.issues if i.code == "broken_link" and i.client == "claude"]
            self.assertTrue(broken, "expected broken_link issue before align")

            report, actions = roots.align(apply=True)

            self.assertFalse([i for i in report.issues if i.code == "broken_link" and i.client == "claude"])
            self.assertTrue(any("Repaired broken link" in a for a in actions))
            self.assertTrue((home / ".claude" / "skills" / "local-skill" / "SKILL.md").is_file())

    def test_align_apply_reports_invalid_skill_name_for_windows_unsafe_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "banner-design"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: ckm:banner-design\n---\n", encoding="utf-8")

            gone = home / "gone"
            gone.mkdir()
            claude_entry = home / ".claude" / "skills" / "banner-design"
            _create_directory_link(claude_entry, gone)
            gone.rmdir()

            roots = WorkspaceRoots.for_home(home)

            pre = roots.audit()
            invalid = [
                i
                for i in pre.issues
                if i.code == "invalid_skill_name" and i.client == "claude" and i.skill_name == "ckm:banner-design"
            ]
            self.assertTrue(invalid, "expected invalid_skill_name issue for Windows-unsafe skill")
            self.assertFalse(
                [
                    i
                    for i in pre.issues
                    if i.code == "missing_exposure" and i.client == "claude" and i.skill_name == "ckm:banner-design"
                ]
            )

            report, actions = roots.align(apply=True)

            self.assertTrue(
                [
                    i
                    for i in report.issues
                    if i.code == "invalid_skill_name" and i.client == "claude" and i.skill_name == "ckm:banner-design"
                ]
            )
            self.assertTrue(any("incompatible skill name" in a and "ckm:banner-design" in a for a in actions))
            self.assertFalse((home / ".claude" / "skills" / "banner-design" / "SKILL.md").is_file())

    def test_align_apply_reports_legacy_copy_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".skills" / "custom" / "local-skill"
            claude_copy = home / ".claude" / "skills" / "local-skill"
            skill_dir.mkdir(parents=True)
            claude_copy.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")
            (claude_copy / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            report, actions = roots.align(apply=True)

            self.assertTrue(claude_copy.is_dir())
            self.assertTrue(
                any(
                    "standalone copy" in a.lower()
                    and "inspect" in a.lower()
                    and "backup" in a.lower()
                    and str(skill_dir) in a
                    for a in actions
                )
            )

    def test_align_apply_updates_managed_link_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo_root = home / ".skills" / "repos" / "nextlevelbuilder" / "ui-ux-pro-max-skill"
            old_skill = repo_root / ".claude" / "skills" / "design"
            current_skill = repo_root / "cli" / "assets" / "skills" / "design"
            for skill_dir in [old_skill, current_skill]:
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: design\n---\n", encoding="utf-8")
            (repo_root / ".git").mkdir()

            _create_directory_link(home / ".agents" / "skills" / "design", old_skill)
            _create_directory_link(home / ".claude" / "skills" / "design", old_skill)
            _create_directory_link(home / ".copilot" / "skills" / "design", old_skill)

            roots = WorkspaceRoots.for_home(home)

            pre = roots.audit()
            self.assertIn(("design", "codex", "target_mismatch"), {(i.skill_name, i.client, i.code) for i in pre.issues})

            report, actions = roots.align(apply=True)

            self.assertFalse([issue for issue in report.issues if issue.skill_name == "design"])
            self.assertEqual((home / ".agents" / "skills" / "design").resolve(strict=False), current_skill.resolve())
            self.assertEqual((home / ".copilot" / "skills" / "design").resolve(strict=False), current_skill.resolve())
            self.assertTrue(any("Updated skill link target for design in codex" in action for action in actions))


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

    def test_bootstrap_self_rejects_invalid_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "banner-design"
            source_root.mkdir(parents=True)
            (source_root / "SKILL.md").write_text("---\nname: ckm:banner-design\n---\n", encoding="utf-8")

            roots = WorkspaceRoots.for_home(home)

            with self.assertRaisesRegex(RuntimeError, "ckm:banner-design"):
                roots.bootstrap_self(source_root)

    def test_bootstrap_self_rejects_invalid_skill_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source_root = home / "projects" / "harden"
            source_root.mkdir(parents=True)
            (source_root / "SKILL.md").write_text(
                "---\n"
                "name: harden\n"
                "description: Make interfaces production-ready: error handling\n"
                "---\n",
                encoding="utf-8",
            )

            roots = WorkspaceRoots.for_home(home)

            with self.assertRaisesRegex(RuntimeError, "Invalid skill frontmatter"):
                roots.bootstrap_self(source_root)


class RemoveCustomSkillTests(unittest.TestCase):
    def test_remove_custom_skill_dry_run_then_apply_removes_empty_source_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            source = home / ".skills" / "custom" / "codex-mem"
            source.mkdir(parents=True)
            _create_directory_link(home / ".agents" / "skills" / "codex-mem", source)

            dry = roots.remove_custom_skill("codex-mem")

            self.assertFalse(dry.applied)
            self.assertIn(source, dry.planned_paths)
            self.assertTrue(source.exists())
            self.assertTrue((home / ".agents" / "skills" / "codex-mem").exists())

            applied = roots.remove_custom_skill("codex-mem", apply=True)

            self.assertTrue(applied.applied)
            self.assertIn(source, applied.removed_paths)
            self.assertFalse(source.exists())
            self.assertFalse((home / ".agents" / "skills" / "codex-mem").exists())

    def test_remove_custom_skill_does_not_delete_non_empty_source_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            source = home / ".skills" / "custom" / "local-skill"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("---\nname: local-skill\n---\n", encoding="utf-8")

            result = roots.remove_custom_skill("local-skill", apply=True)

            self.assertTrue(source.exists())
            self.assertTrue(any("non-empty custom source" in item for item in result.skipped))


class RepoInstallTests(unittest.TestCase):
    def test_install_repo_skills_rejects_client_incompatible_skill_name(self) -> None:
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

            with self.assertRaisesRegex(RuntimeError, "ckm:banner-design"):
                roots.install_repo_skills(
                    repo_slug="nextlevelbuilder/ui-ux-pro-max-skill",
                    skill_paths=[".claude/skills/banner-design"],
                )

    def test_install_repo_skills_rejects_invalid_skill_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            repo_root = home / ".skills" / "repos" / "pbakaus" / "impeccable"
            skill_dir = repo_root / ".codex" / "skills" / "harden"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: harden\n"
                "description: Make interfaces production-ready: error handling\n"
                "---\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Invalid skill frontmatter"):
                roots.install_repo_skills(
                    repo_slug="pbakaus/impeccable",
                    skill_paths=[".codex/skills/harden"],
                )

    def test_install_plugin_bundle_rejects_invalid_exported_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            source_root = home / "projects" / "ui-ux-pro-max-skill"
            (source_root / ".claude-plugin").mkdir(parents=True)
            (source_root / "skills" / "banner-design").mkdir(parents=True)
            (source_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (source_root / "skills" / "banner-design" / "SKILL.md").write_text(
                "---\nname: ckm:banner-design\n---\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "ckm:banner-design"):
                roots.install_plugin_bundle(
                    publisher="nextlevelbuilder",
                    name="ui-ux-pro-max-skill",
                    source_root=source_root,
                )

    def test_install_plugin_bundle_rejects_invalid_exported_skill_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            source_root = home / "projects" / "impeccable"
            (source_root / ".claude-plugin").mkdir(parents=True)
            (source_root / "skills" / "harden").mkdir(parents=True)
            (source_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (source_root / "skills" / "harden" / "SKILL.md").write_text(
                "---\n"
                "name: harden\n"
                "description: Make interfaces production-ready: error handling\n"
                "---\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "invalid frontmatter"):
                roots.install_plugin_bundle(
                    publisher="pbakaus",
                    name="impeccable",
                    source_root=source_root,
                )

    def test_install_plugin_bundle_replaces_existing_client_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            legacy_skill = home / ".skills" / "repos" / "superpowers" / "skills" / "brainstorming"
            source_root = home / "projects" / "superpowers"
            managed_skill = source_root / "skills" / "brainstorming"
            legacy_skill.mkdir(parents=True)
            managed_skill.mkdir(parents=True)
            (legacy_skill / "SKILL.md").write_text("---\nname: brainstorming\n---\nlegacy\n", encoding="utf-8")
            (managed_skill / "SKILL.md").write_text("---\nname: brainstorming\n---\nmanaged\n", encoding="utf-8")
            (source_root / ".codex-plugin").mkdir()
            (source_root / ".codex-plugin" / "plugin.json").write_text('{"name":"superpowers"}', encoding="utf-8")
            _create_directory_link(home / ".claude" / "skills" / "brainstorming", legacy_skill)

            roots.install_plugin_bundle(
                publisher="obra",
                name="superpowers",
                source_root=source_root,
                clients=["claude"],
                native=False,
            )

            self.assertIn("managed", (home / ".claude" / "skills" / "brainstorming" / "SKILL.md").read_text(encoding="utf-8"))

    def test_native_plugin_install_skips_registered_marketplace_add(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)
            bundle_root = home / ".skills" / "plugins" / "obra" / "superpowers"
            (bundle_root / ".codex-plugin").mkdir(parents=True)
            (bundle_root / "skills" / "using-superpowers").mkdir(parents=True)
            (bundle_root / ".codex-plugin" / "plugin.json").write_text(
                '{"name":"superpowers","version":"6.0.3"}',
                encoding="utf-8",
            )
            (bundle_root / "skills" / "using-superpowers" / "SKILL.md").write_text(
                "---\nname: using-superpowers\n---\n",
                encoding="utf-8",
            )
            bundle = roots._plugin_bundle_from_path(
                bundle_root,
                publisher="obra",
                name="superpowers",
                bundle_type="plugin-managed",
            )

            def fake_run_captured(args: list[str], cwd=None, timeout=120):
                if args[2:4] == ["marketplace", "list"]:
                    return True, "superpowers-marketplace C:\\marketplace"
                return True, json.dumps(
                    {
                        "installed": [
                            {
                                "pluginId": "superpowers@superpowers-marketplace",
                                "name": "superpowers",
                            }
                        ]
                    }
                )

            with mock.patch("skill_install_plus_plus.manager.shutil.which", return_value="codex"), mock.patch(
                "skill_install_plus_plus.manager._run_captured",
                side_effect=fake_run_captured,
            ), mock.patch("skill_install_plus_plus.manager._run_inherited", return_value=0) as run_inherited:
                notes = roots._apply_native_plugin_installs(
                    bundle,
                    ["codex"],
                    marketplace_source="obra/superpowers-marketplace",
                    marketplace_name="superpowers-marketplace",
                )

            run_inherited.assert_called_once()
            self.assertIn("marketplace add skipped", notes[0])

    def test_install_repo_skills_clones_when_repo_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)

            # The repo directory does NOT exist yet — install must clone it.
            repo_root = home / ".skills" / "repos" / "acme" / "toolbox"

            def fake_clone(args: list[str], cwd=None) -> str:
                # Simulate what git clone would do: create the directory with a skill.
                skill_dir = Path(args[-1]) / "skills" / "my-skill"
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
                return ""

            with mock.patch("skill_install_plus_plus.manager._run_git", side_effect=fake_clone) as run_git:
                result = roots.install_repo_skills(
                    repo_slug="acme/toolbox",
                    skill_paths=["skills/my-skill"],
                )

            run_git.assert_called_once()
            clone_args = run_git.call_args[0][0]
            # clone_args is the first positional argument passed to _run_git,
            # which is the full list: ["git", "clone", "--depth", "1", "--branch", "main", <url>, <dest>]
            self.assertEqual(clone_args[0], "git")
            self.assertEqual(clone_args[1], "clone")
            self.assertIn("--branch", clone_args)
            self.assertEqual(clone_args[clone_args.index("--branch") + 1], "main")
            self.assertIn("acme/toolbox", clone_args[-2])  # URL is second-to-last arg
            self.assertEqual(clone_args[-1], str(repo_root))

            self.assertEqual(len(result.installed), 1)
            self.assertEqual(result.installed[0].name, "my-skill")
            self.assertTrue((home / ".claude" / "skills" / "my-skill" / "SKILL.md").is_file())

    def test_install_repo_skills_pulls_when_repo_exists_and_update_existing_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            roots = WorkspaceRoots.for_home(home)

            repo_root = home / ".skills" / "repos" / "acme" / "toolbox"
            skill_dir = repo_root / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
            (repo_root / ".git").mkdir()  # mark as a git repo

            with mock.patch("skill_install_plus_plus.manager._run_git", return_value="Already up to date.") as run_git:
                roots.install_repo_skills(
                    repo_slug="acme/toolbox",
                    skill_paths=["skills/my-skill"],
                    update_existing=True,
                )

            run_git.assert_called_once_with(["git", "pull"], cwd=repo_root)


if __name__ == "__main__":
    unittest.main()
