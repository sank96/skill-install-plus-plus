from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from skill_install_plus_plus.manager import WorkspaceRoots


def _default_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def _default_source() -> Path:
    configured = os.environ.get("SKILL_INSTALL_PLUS_PLUS_PROJECT_ROOT")
    if configured:
        return Path(configured)
    return Path.cwd()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workspace skill manager.")
    parser.add_argument("--home", type=Path, default=_default_home(), help="Override home directory for testing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("audit", help="Audit current skill state.")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Install this skill into the local profile.")
    bootstrap_parser.add_argument("--source", type=Path, default=_default_source(), help="Project root containing SKILL.md.")
    bootstrap_parser.add_argument("--client", action="append", choices=["codex", "claude", "copilot"], help="Client targets. Defaults to all.")

    install_parser = subparsers.add_parser("install", help="Install skill(s) from a GitHub repo.")
    install_parser.add_argument("--repo", required=True, help="owner/repo")
    install_parser.add_argument("--path", action="append", required=True, help="Skill path inside repo.")
    install_parser.add_argument("--client", action="append", choices=["codex", "claude", "copilot"], help="Client targets. Defaults to all.")
    install_parser.add_argument("--ref", default="main")
    install_parser.add_argument("--update-existing", action="store_true")

    install_plugin_parser = subparsers.add_parser("install-plugin", help="Install a managed plugin bundle.")
    install_plugin_parser.add_argument("--publisher", required=True)
    install_plugin_parser.add_argument("--name", required=True)
    install_plugin_parser.add_argument("--source", type=Path)
    install_plugin_parser.add_argument("--repo")
    install_plugin_parser.add_argument("--client", action="append", choices=["codex", "claude", "copilot"], help="Client targets. Defaults to all.")
    install_plugin_parser.add_argument("--ref", default="main")
    install_plugin_parser.add_argument("--update-existing", action="store_true")
    install_plugin_parser.add_argument("--export-skill", action="append", help="Restrict exported skills to a subset.")
    install_plugin_parser.add_argument("--no-native", action="store_true", help="Skip native client plugin install/update and only expose exported skills.")
    install_plugin_parser.add_argument("--native-dry-run", action="store_true", help="Print native client plugin commands without running them.")
    install_plugin_parser.add_argument("--native-marketplace-source", help="Override the source passed to native `plugin marketplace add`.")
    install_plugin_parser.add_argument("--native-marketplace-name", help="Override the marketplace name used in native plugin selectors.")
    install_plugin_parser.add_argument("--native-plugin-name", help="Override the plugin name used in native plugin selectors.")
    install_plugin_parser.add_argument("--native-plugin-source", help="Override direct native plugin source for clients that support repository installs.")

    remove_parser = subparsers.add_parser("remove", help="Remove a managed custom skill.")
    remove_parser.add_argument("name", help="Skill name or custom directory name.")
    remove_parser.add_argument("--client", action="append", choices=["codex", "claude", "copilot"], help="Client targets. Defaults to all.")
    remove_parser.add_argument("--apply", action="store_true", help="Apply removals. Without this flag, only prints a plan.")
    remove_parser.add_argument("--force", action="store_true", help="Also remove non-empty standalone custom source directories.")

    update_parser = subparsers.add_parser("update", help="Run git pull on managed repos.")
    update_parser.add_argument("--repo", help="owner/repo")

    align_parser = subparsers.add_parser("align", help="Align client exposures with source-of-truth skills.")
    align_parser.add_argument("--apply", action="store_true", help="Apply non-destructive repairs.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    roots = WorkspaceRoots.for_home(args.home)

    if args.command == "audit":
        print(roots.audit().format_text())
        return 0

    if args.command == "bootstrap":
        result = roots.bootstrap_self(source_root=args.source, clients=args.client)
        print(f"Managed source: {result.managed_source}")
        for path in result.created_paths:
            print(f"Created path: {path}")
        for item in result.skipped_paths:
            print(f"Skipped: {item}")
        for path in result.policy_files:
            print(f"Policy file: {path}")
        return 0

    if args.command == "install":
        result = roots.install_repo_skills(
            repo_slug=args.repo,
            skill_paths=args.path,
            clients=args.client,
            ref=args.ref,
            update_existing=args.update_existing,
        )
        print(f"Repo root: {result.repo_root}")
        for source in result.installed:
            print(f"Installed source: {source.name} ({source.relative_path})")
        for path in result.created_exposures:
            print(f"Created exposure: {path}")
        for path in result.skipped_exposures:
            print(f"Exposure already satisfied: {path}")
        return 0

    if args.command == "install-plugin":
        result = roots.install_plugin_bundle(
            publisher=args.publisher,
            name=args.name,
            source_root=args.source,
            repo_slug=args.repo,
            clients=args.client,
            ref=args.ref,
            update_existing=args.update_existing,
            export_skills=args.export_skill,
            native=not args.no_native,
            native_dry_run=args.native_dry_run,
            native_marketplace_source=args.native_marketplace_source,
            native_marketplace_name=args.native_marketplace_name,
            native_plugin_name=args.native_plugin_name,
            native_plugin_source=args.native_plugin_source,
        )
        print(f"Installed plugin bundle: {result.bundle_root}")
        print(f"Manifest type: {result.bundle.manifest_type}")
        if result.bundle.exported_skills:
            print(f"Exported skills: {', '.join(result.bundle.exported_skills)}")
        else:
            print("Exported skills: none")
        for path in result.created_exposures:
            print(f"Created exposure: {path}")
        for path in result.skipped_exposures:
            print(f"Exposure already satisfied: {path}")
        for note in result.notes:
            print(f"Note: {note}")
        for note in result.native_notes:
            print(f"Native: {note}")
        return 0

    if args.command == "remove":
        result = roots.remove_custom_skill(
            skill_name=args.name,
            clients=args.client,
            apply=args.apply,
            force=args.force,
        )
        prefix = "Removed" if result.applied else "Would remove"
        for path in result.removed_paths if result.applied else result.planned_paths:
            print(f"{prefix}: {path}")
        for item in result.skipped:
            print(f"Skipped: {item}")
        if not result.applied:
            print("Dry run only. Re-run with --apply to remove these paths.")
        return 0

    if args.command == "update":
        results = roots.update_repos(repo_slug=args.repo)
        for result in results:
            status = "OK" if result.success else "FAIL"
            print(f"[{status}] {result.repo_root}")
            if result.output:
                print(result.output)
        return 0 if all(item.success for item in results) else 1

    if args.command == "align":
        report, actions = roots.align(apply=args.apply)
        print(report.format_text())
        if actions:
            print("")
            print("Alignment actions:")
            for action in actions:
                print(f"- {action}")
        return 0

    raise RuntimeError(f"Unsupported command: {args.command}")
