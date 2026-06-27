from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable
import yaml


CLIENT_NAMES = ("codex", "claude", "copilot")
CLIENT_SKILL_ROOT_PRIORITY = {
    "codex": ((".codex", "skills"), (".agents", "skills")),
    "claude": ((".claude", "skills"),),
    "copilot": ((".copilot", "skills"), (".github", "skills")),
}
CLIENT_SKILL_ROOTS = {
    tuple(root_parts): client
    for client, roots in CLIENT_SKILL_ROOT_PRIORITY.items()
    for root_parts in roots
}
POLICY_MARKER = "<!-- skill-management-policy -->"
CLIENT_SAFE_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._ -]+$")
CLIENT_SAFE_SKILL_NAME_RULE = "letters, numbers, hyphens, underscores, dots, and spaces"
WINDOWS_INVALID_PATH_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED_PATH_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class SkillSource:
    name: str
    path: Path
    source_type: str
    relative_path: str
    owner: str | None = None
    repo: str | None = None
    client_paths: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginBundle:
    publisher: str
    name: str
    path: Path
    bundle_type: str
    manifest_type: str
    exported_skills: list[str] = field(default_factory=list)
    exported_skill_dirs: dict[str, Path] = field(default_factory=dict)
    owner: str | None = None
    repo: str | None = None
    detected_client: str | None = None


@dataclass(frozen=True)
class ClientSkill:
    client: str
    skill_name: str
    skill_dir: Path
    top_entry: Path
    direct: bool
    top_entry_is_link: bool
    top_entry_link_type: str
    resolved_skill_dir: Path


@dataclass(frozen=True)
class AuditIssue:
    skill_name: str
    client: str
    code: str
    message: str
    path: Path | None = None
    target: Path | None = None
    proposed_action: str | None = None


@dataclass(frozen=True)
class RepoRecord:
    owner: str
    repo: str
    repo_root: str
    skills: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PluginRecord:
    publisher: str
    name: str
    bundle_root: str
    manifest_type: str
    exported_skills: list[str] = field(default_factory=list)
    clients: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistryState:
    version: int
    repos: list[RepoRecord]
    plugins: list[PluginRecord] = field(default_factory=list)


@dataclass(frozen=True)
class AuditReport:
    sources: list[SkillSource]
    plugin_bundles: list[PluginBundle]
    client_skills: dict[str, list[ClientSkill]]
    issues: list[AuditIssue]
    classification_counts: dict[str, int] = field(default_factory=dict)

    def format_text(self) -> str:
        lines = [
            f"Managed sources: {len(self.sources)}",
            f"Managed plugin bundles: {self.classification_counts.get('plugin-managed', 0)}",
            f"Hybrid bundles: {self.classification_counts.get('hybrid', 0)}",
            f"Manual bundles: {self.classification_counts.get('manual', 0)}",
            f"Audit issues: {len(self.issues)}",
        ]
        if not self.issues:
            lines.append("No issues detected.")
            return "\n".join(lines)
        lines.append("")
        for issue in sorted(self.issues, key=lambda item: (item.skill_name, item.client, item.code)):
            where = f" [{issue.client}]" if issue.client else ""
            lines.append(f"- {issue.skill_name}{where}: {issue.code} - {issue.message}")
            if issue.path:
                lines.append(f"  path: {issue.path}")
            if issue.target:
                lines.append(f"  target: {issue.target}")
            if issue.proposed_action:
                lines.append(f"  proposed: {issue.proposed_action}")
        return "\n".join(lines)


@dataclass(frozen=True)
class InstallResult:
    repo_root: Path
    installed: list[SkillSource]
    created_exposures: list[Path]
    skipped_exposures: list[Path]


@dataclass(frozen=True)
class PluginInstallResult:
    bundle_root: Path
    bundle: PluginBundle
    created_exposures: list[Path]
    skipped_exposures: list[Path]
    notes: list[str] = field(default_factory=list)
    native_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateResult:
    repo_root: Path
    success: bool
    output: str


@dataclass(frozen=True)
class BootstrapResult:
    skill_name: str
    managed_source: Path
    created_paths: list[Path]
    skipped_paths: list[str]
    policy_files: list[Path]


@dataclass(frozen=True)
class RemoveResult:
    skill_name: str
    planned_paths: list[Path]
    removed_paths: list[Path]
    skipped: list[str] = field(default_factory=list)
    applied: bool = False


def _is_junction(path: Path) -> bool:
    try:
        return os.path.isjunction(path)
    except AttributeError:
        return False


def _is_link(path: Path) -> bool:
    return path.is_symlink() or _is_junction(path) or (_path_exists_or_links(path) and not path.exists())


def _link_type(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if _is_junction(path):
        return "junction"
    return "directory"


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or "Git command failed.")
    return result.stdout.strip()


def _run_captured(args: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, result.stdout.strip()


def _run_inherited(args: list[str], cwd: Path | None = None) -> int:
    try:
        result = subprocess.run(args, cwd=str(cwd) if cwd else None, check=False)
    except FileNotFoundError:
        return 127
    return result.returncode


def _format_command(args: list[str]) -> str:
    def quote(part: str) -> str:
        if not part or any(char.isspace() for char in part) or any(char in part for char in ['"', "'"]):
            return '"' + part.replace('"', '\\"') + '"'
        return part

    return " ".join(quote(str(part)) for part in args)


def _read_skill_name(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise RuntimeError(f"SKILL.md not found at {skill_md}")
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            if value:
                return value
    return skill_dir.name


def _extract_frontmatter(skill_text: str) -> tuple[str | None, str | None]:
    lines = skill_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), None
    return None, "invalid frontmatter: missing closing delimiter."


def _format_yaml_error(exc: yaml.YAMLError) -> str:
    problem = getattr(exc, "problem", None)
    mark = getattr(exc, "problem_mark", None)
    if problem and mark:
        return f"invalid YAML: {problem} at line {mark.line + 1} column {mark.column + 1}"
    return f"invalid YAML: {' '.join(str(exc).split())}"


def _skill_frontmatter_error(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise RuntimeError(f"SKILL.md not found at {skill_md}")

    frontmatter, delimiter_error = _extract_frontmatter(skill_md.read_text(encoding="utf-8"))
    if delimiter_error:
        return delimiter_error
    if frontmatter is None:
        return None

    try:
        payload = yaml.safe_load(frontmatter) if frontmatter.strip() else {}
    except yaml.YAMLError as exc:
        return _format_yaml_error(exc)

    if payload is not None and not isinstance(payload, dict):
        return "invalid frontmatter: expected a YAML mapping."
    return None


def _is_client_safe_skill_name(skill_name: str) -> bool:
    return bool(CLIENT_SAFE_SKILL_NAME_PATTERN.fullmatch(skill_name))


def _suggest_client_safe_skill_name(skill_name: str, source_path: Path) -> str:
    candidate = source_path.name.strip()
    if _is_client_safe_skill_name(candidate):
        return candidate

    normalized = re.sub(r"[^A-Za-z0-9._ -]+", "-", skill_name)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip(" .-_")
    return normalized or "skill"


def _path_exists_or_links(path: Path) -> bool:
    return os.path.lexists(path)


def _is_windows_safe_dir_name(name: str) -> bool:
    if not name or any(char in WINDOWS_INVALID_PATH_CHARS for char in name):
        return False
    if name[-1] in {" ", "."}:
        return False
    return name.split(".")[0].upper() not in WINDOWS_RESERVED_PATH_NAMES


def _exposure_dir_name(skill_name: str, source_path: Path) -> str:
    if os.name == "nt" and not _is_windows_safe_dir_name(skill_name):
        return source_path.name
    return skill_name


def _remove_directory_link(path: Path) -> None:
    if path.is_symlink() or (_path_exists_or_links(path) and not path.exists()):
        path.unlink()
        return
    path.rmdir()


def _ensure_directory_link(link_path: Path, target_path: Path, replace_existing_link: bool = False) -> tuple[bool, str]:
    if link_path == target_path:
        link_path.mkdir(parents=True, exist_ok=True)
        return False, f"Destination already uses {link_path}."

    if _path_exists_or_links(link_path):
        if _safe_resolve(link_path) == _safe_resolve(target_path):
            return False, f"Destination already present: {link_path}"
        if replace_existing_link and _is_link(link_path):
            _remove_directory_link(link_path)
            _create_directory_link(link_path, target_path)
            return True, f"Updated managed link: {link_path}"
        raise RuntimeError(f"Destination already exists and points elsewhere: {link_path}")

    _create_directory_link(link_path, target_path)
    return True, f"Created managed link: {link_path}"


def _append_block_if_missing(path: Path, marker: str, block: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    normalized = existing.replace("\r\n", "\n")
    if marker in normalized:
        return False

    content = normalized.rstrip()
    if content:
        content += "\n\n"
    content += f"{marker}\n{block.strip()}\n"
    path.write_text(content, encoding="utf-8")
    return True


def _create_directory_link(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if _path_exists_or_links(link_path) or link_path.is_symlink():
        raise RuntimeError(f"Destination already exists: {link_path}")
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return
    os.symlink(target_path, link_path, target_is_directory=True)


def _plugin_manifest_type(bundle_root: Path) -> str:
    if (bundle_root / ".codex-plugin" / "plugin.json").is_file():
        return "codex"
    if (bundle_root / ".claude-plugin" / "plugin.json").is_file():
        return "claude"
    return "none"


def _read_json_if_exists(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_skill_manifest(repo_root: Path) -> dict:
    payload = _read_json_if_exists(repo_root / "skill.json")
    return payload if isinstance(payload, dict) else {}


def _repo_declared_clients(repo_root: Path) -> set[str]:
    payload = _repo_skill_manifest(repo_root)
    platforms = payload.get("platforms")
    if not isinstance(platforms, list):
        return set()
    return {
        str(platform).lower()
        for platform in platforms
        if str(platform).lower() in CLIENT_NAMES
    }


def _repo_primary_skill_name(repo_root: Path) -> str | None:
    payload = _repo_skill_manifest(repo_root)
    name = payload.get("name")
    return str(name) if name else None


def _plugin_like_structure(bundle_root: Path) -> bool:
    if _plugin_manifest_type(bundle_root) != "none":
        return True
    has_skills = (bundle_root / "skills").is_dir()
    has_bundle_signals = (bundle_root / "agents").is_dir() or (bundle_root / "hooks").is_dir()
    return has_skills and has_bundle_signals


def _exported_skill_dirs(bundle_root: Path) -> dict[str, Path]:
    exported: dict[str, Path] = {}
    for skills_root in (bundle_root / "skills", bundle_root / "plugin" / "skills"):
        if not skills_root.is_dir():
            continue
        for skill_md in skills_root.glob("*/SKILL.md"):
            skill_dir = skill_md.parent
            exported.setdefault(_read_skill_name(skill_dir), skill_dir)
    return dict(sorted(exported.items(), key=lambda item: item[0]))


def _manual_bundle_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    if not root.is_dir():
        return candidates
    ignored = {
        ".sandbox",
        ".sandbox-bin",
        ".sandbox-secrets",
        ".tmp",
        "agents",
        "archived_sessions",
        "automations",
        "cache",
        "codex-mem",
        "get-shit-done",
        "log",
        "memories",
        "plugins",
        "rules",
        "sessions",
        "skills",
        "sqlite",
        "tmp",
        "vendor_imports",
    }
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        lowered = child.name.lower()
        if child.name in ignored or ".backup-" in lowered or lowered.startswith("backup-"):
            continue
        for manifest in child.rglob("plugin.json"):
            if manifest.parent.name not in {".claude-plugin", ".codex-plugin"}:
                continue
            bundle_root = manifest.parent.parent
            if bundle_root not in candidates:
                candidates.append(bundle_root)
    filtered: list[Path] = []
    for candidate in sorted(candidates, key=lambda item: (len(item.parts), str(item)), reverse=True):
        candidate_exported = bool(_exported_skill_dirs(candidate))
        skip = False
        for kept in filtered:
            if candidate in kept.parents and bool(_exported_skill_dirs(kept)) and not candidate_exported:
                skip = True
                break
        if not skip:
            filtered.append(candidate)
    return sorted(filtered)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _plugin_provider_skill_client(relative_path: Path) -> str | None:
    parts = relative_path.parts
    if len(parts) < 5 or parts[0] != "plugins" or parts[-2] != "skills":
        return None
    provider = parts[1].lower()
    return provider if provider in CLIENT_NAMES else None


def _repo_skill_client(relative_path: Path) -> str | None:
    parts = relative_path.parts
    if len(parts) >= 3:
        client = CLIENT_SKILL_ROOTS.get((parts[0], parts[1]))
        if client:
            return client
    return _plugin_provider_skill_client(relative_path)


def _is_provider_specific_skill_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    if len(parts) >= 3 and parts[0].startswith(".") and parts[1] == "skills":
        return True
    if len(parts) >= 5 and parts[0] == "plugins" and parts[-2] == "skills":
        return True
    if len(parts) >= 4 and parts[0] == "packages" and parts[2] == "skills":
        return True
    return False


def _client_path_priority(client: str, relative_path: Path) -> int:
    root = tuple(relative_path.parts[:2])
    priority = list(CLIENT_SKILL_ROOT_PRIORITY[client])
    if root in priority:
        return priority.index(root)
    if _plugin_provider_skill_client(relative_path) == client:
        return len(priority)
    return len(priority) + 100


@dataclass(frozen=True)
class WorkspaceRoots:
    home: Path
    skills_root: Path
    repos_root: Path
    custom_root: Path
    plugins_root: Path
    registry_path: Path
    codex_root: Path
    claude_root: Path
    copilot_root: Path
    _native_plugin_list_cache: dict[tuple[str, str, str], tuple[bool, str]] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    @classmethod
    def for_home(cls, home: Path) -> "WorkspaceRoots":
        skills_root = home / ".skills"
        return cls(
            home=home,
            skills_root=skills_root,
            repos_root=skills_root / "repos",
            custom_root=skills_root / "custom",
            plugins_root=skills_root / "plugins",
            registry_path=skills_root / "registry.json",
            codex_root=home / ".agents" / "skills",
            claude_root=home / ".claude" / "skills",
            copilot_root=home / ".copilot" / "skills",
        )

    def client_roots(self) -> dict[str, Path]:
        return {
            "codex": self.codex_root,
            "claude": self.claude_root,
            "copilot": self.copilot_root,
        }

    def ensure_root_directories(self) -> None:
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.custom_root.mkdir(parents=True, exist_ok=True)
        self.repos_root.mkdir(parents=True, exist_ok=True)
        self.plugins_root.mkdir(parents=True, exist_ok=True)
        for client_root in self.client_roots().values():
            client_root.mkdir(parents=True, exist_ok=True)
        (self.home / ".codex").mkdir(parents=True, exist_ok=True)
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        (self.home / ".copilot").mkdir(parents=True, exist_ok=True)

    def bootstrap_self(self, source_root: Path, clients: Iterable[str] | None = None) -> BootstrapResult:
        self.ensure_root_directories()
        client_list = self._normalize_clients(clients)
        self._ensure_skill_frontmatter_is_valid(source_root)
        skill_name = _read_skill_name(source_root)
        self._ensure_skill_name_is_client_safe(skill_name, source_root, client_list)
        managed_source = self.custom_root / _exposure_dir_name(skill_name, source_root)

        created_paths: list[Path] = []
        skipped_paths: list[str] = []

        created, message = _ensure_directory_link(managed_source, source_root)
        if created:
            created_paths.append(managed_source)
        else:
            skipped_paths.append(message)

        for client in client_list:
            created, path_or_message = self._apply_skill_source_exposure(
                source=SkillSource(
                    name=skill_name,
                    path=managed_source,
                    source_type="custom",
                    relative_path=skill_name,
                ),
                client=client,
            )
            if created and isinstance(path_or_message, Path):
                created_paths.append(path_or_message)
            elif isinstance(path_or_message, str):
                skipped_paths.append(path_or_message)

        policy_files = list(self._policy_paths_for_clients(client_list).values())
        for client, path in self._policy_paths_for_clients(client_list).items():
            _append_block_if_missing(path, POLICY_MARKER, self._policy_block(client))

        return BootstrapResult(
            skill_name=skill_name,
            managed_source=managed_source,
            created_paths=created_paths,
            skipped_paths=skipped_paths,
            policy_files=policy_files,
        )

    def remove_custom_skill(
        self,
        skill_name: str,
        clients: Iterable[str] | None = None,
        apply: bool = False,
        force: bool = False,
    ) -> RemoveResult:
        client_list = self._normalize_clients(clients)
        source_path = self._custom_skill_path_for_name(skill_name)
        planned_paths: list[Path] = []
        removed_paths: list[Path] = []
        skipped: list[str] = []

        if source_path is None:
            return RemoveResult(
                skill_name=skill_name,
                planned_paths=[],
                removed_paths=[],
                skipped=[f"Managed custom skill not found: {skill_name}"],
                applied=apply,
            )

        source_target = _safe_resolve(source_path)
        for client in client_list:
            client_root = self.client_roots()[client]
            if not client_root.is_dir():
                continue
            for entry in sorted(client_root.iterdir()):
                if not self._entry_matches_removed_custom_skill(entry, skill_name, source_target):
                    continue
                if not _is_link(entry):
                    skipped.append(f"Skipped standalone client copy in {client}: {entry}")
                    continue
                planned_paths.append(entry)
                if apply:
                    self._remove_path_entry(entry)
                    removed_paths.append(entry)

        planned_paths.append(source_path)
        if apply:
            removed_source = self._remove_custom_source_path(source_path, force=force)
            if removed_source:
                removed_paths.append(source_path)
            else:
                skipped.append(f"Skipped non-empty custom source without --force: {source_path}")

        return RemoveResult(
            skill_name=skill_name,
            planned_paths=planned_paths,
            removed_paths=removed_paths,
            skipped=skipped,
            applied=apply,
        )

    def _custom_skill_path_for_name(self, skill_name: str) -> Path | None:
        direct = self.custom_root / skill_name
        if _path_exists_or_links(direct):
            return direct
        for source in self._discover_custom_sources():
            if source.name == skill_name:
                return source.path
        return None

    def _entry_matches_removed_custom_skill(self, entry: Path, skill_name: str, source_target: Path) -> bool:
        if entry.name == skill_name:
            return True
        if _safe_resolve(entry) == source_target:
            return True
        skill_md = entry / "SKILL.md"
        if skill_md.is_file():
            try:
                return _read_skill_name(entry) == skill_name
            except RuntimeError:
                return False
        return False

    def _remove_custom_source_path(self, source_path: Path, force: bool = False) -> bool:
        if _is_link(source_path):
            self._remove_path_entry(source_path)
            return True
        if source_path.is_dir():
            try:
                source_path.rmdir()
                return True
            except OSError:
                if not force:
                    return False
                shutil.rmtree(source_path)
                return True
        if source_path.is_file():
            source_path.unlink()
            return True
        if _path_exists_or_links(source_path):
            self._remove_path_entry(source_path)
            return True
        return False

    def _remove_path_entry(self, path: Path) -> None:
        if path.is_symlink() or (_path_exists_or_links(path) and not path.exists()):
            path.unlink()
            return
        if path.is_dir():
            path.rmdir()
            return
        path.unlink()

    def discover_sources(self) -> list[SkillSource]:
        discovered = self._discover_custom_sources() + self._discover_repo_sources()
        return sorted(discovered, key=lambda item: (item.name, item.relative_path, str(item.path)))

    def discover_plugin_bundles(self) -> list[PluginBundle]:
        bundles = self._discover_plugin_source_bundles() + self._discover_hybrid_repo_bundles()
        return sorted(bundles, key=lambda item: (item.bundle_type, item.publisher, item.name, str(item.path)))

    def _looks_like_repo_root(self, path: Path) -> bool:
        return any(
            [
                (path / ".git").exists(),
                (path / "skills").is_dir(),
                (path / ".claude-plugin").is_dir(),
                (path / ".codex-plugin").is_dir(),
                (path / "SKILL.md").is_file(),
                (path / "package.json").is_file(),
            ]
        )

    def _iter_repo_roots(self) -> Iterable[tuple[str | None, str, Path]]:
        if not self.repos_root.is_dir():
            return []

        repo_roots: list[tuple[str | None, str, Path]] = []
        for first_level in sorted(path for path in self.repos_root.iterdir() if path.is_dir()):
            if self._looks_like_repo_root(first_level):
                repo_roots.append((None, first_level.name, first_level))
                continue
            for second_level in sorted(path for path in first_level.iterdir() if path.is_dir()):
                if self._looks_like_repo_root(second_level):
                    repo_roots.append((first_level.name, second_level.name, second_level))
        return repo_roots

    def _discover_custom_sources(self) -> list[SkillSource]:
        discovered: list[SkillSource] = []
        if not self.custom_root.is_dir():
            return discovered
        for skill_md in sorted(self.custom_root.glob("*/SKILL.md")):
            skill_dir = skill_md.parent
            discovered.append(
                SkillSource(
                    name=_read_skill_name(skill_dir),
                    path=skill_dir,
                    source_type="custom",
                    relative_path=skill_dir.name,
                )
            )
        return discovered

    def _discover_repo_sources(self) -> list[SkillSource]:
        discovered: list[SkillSource] = []
        for owner, repo, repo_root in self._iter_repo_roots():
            declared_clients = _repo_declared_clients(repo_root)
            primary_skill_name = _repo_primary_skill_name(repo_root)
            provider_sources: dict[str, dict[str, Path]] = {}
            provider_relative_paths: dict[str, str] = {}
            generic_sources: list[SkillSource] = []
            for skill_md in sorted(repo_root.rglob("SKILL.md")):
                skill_dir = skill_md.parent
                relative_path = skill_dir.relative_to(repo_root)
                client = _repo_skill_client(relative_path)
                if client:
                    skill_name = _read_skill_name(skill_dir)
                    client_paths = provider_sources.setdefault(skill_name, {})
                    current = client_paths.get(client)
                    if current is None or _client_path_priority(client, relative_path) < _client_path_priority(
                        client,
                        current.relative_to(repo_root),
                    ):
                        client_paths[client] = skill_dir
                    provider_relative_paths.setdefault(skill_name, relative_path.as_posix())
                    continue
                if _is_provider_specific_skill_path(relative_path):
                    continue
                generic_sources.append(
                    SkillSource(
                        name=_read_skill_name(skill_dir),
                        path=skill_dir,
                        source_type="repo",
                        relative_path=relative_path.as_posix(),
                        owner=owner,
                        repo=repo,
                    )
                )
            generic_sources_by_name: dict[str, SkillSource] = {
                source.name: source
                for source in generic_sources
            }
            provider_skill_names = set(provider_sources)
            discovered.extend(source for source in generic_sources if source.name not in provider_skill_names)
            for skill_name, client_paths in provider_sources.items():
                generic_source = generic_sources_by_name.get(skill_name)
                provider_fallback = next(iter(client_paths.values())) if skill_name == primary_skill_name else None
                ordered_client_paths = {}
                for client in CLIENT_NAMES:
                    if client in client_paths:
                        ordered_client_paths[client] = client_paths[client]
                    elif generic_source is not None:
                        ordered_client_paths[client] = generic_source.path
                    elif provider_fallback is not None and client in declared_clients:
                        ordered_client_paths[client] = provider_fallback
                ordered_client_paths = {
                    client: path
                    for client, path in ordered_client_paths.items()
                    if path is not None
                }
                canonical_path = next(iter(ordered_client_paths.values()))
                discovered.append(
                    SkillSource(
                        name=skill_name,
                        path=canonical_path,
                        source_type="repo",
                        relative_path=canonical_path.relative_to(repo_root).as_posix(),
                        owner=owner,
                        repo=repo,
                        client_paths=ordered_client_paths,
                    )
                )
        return discovered

    def _discover_plugin_source_bundles(self) -> list[PluginBundle]:
        bundles: list[PluginBundle] = []
        if not self.plugins_root.is_dir():
            return bundles
        for publisher_dir in sorted(path for path in self.plugins_root.iterdir() if path.is_dir()):
            for bundle_root in sorted(path for path in publisher_dir.iterdir() if path.is_dir()):
                if not _plugin_like_structure(bundle_root):
                    continue
                bundles.append(
                    self._plugin_bundle_from_path(
                        bundle_root,
                        publisher=publisher_dir.name,
                        name=bundle_root.name,
                        bundle_type="plugin-managed",
                    )
                )
        return bundles

    def _discover_hybrid_repo_bundles(self) -> list[PluginBundle]:
        bundles: list[PluginBundle] = []
        for owner, repo, repo_root in self._iter_repo_roots():
            if not _plugin_like_structure(repo_root):
                continue
            bundles.append(
                self._plugin_bundle_from_path(
                    repo_root,
                    publisher=owner or repo,
                    name=repo,
                    bundle_type="hybrid",
                    owner=owner,
                    repo=repo,
                )
            )
        return bundles

    def _discover_manual_bundles(self) -> list[PluginBundle]:
        scan_roots: list[tuple[Path, str]] = [
            (self.home / ".codex", "codex"),
            (self.home / ".agents", "codex"),
            (self.home / ".claude", "claude"),
        ]
        seen: set[Path] = set()
        bundles: list[PluginBundle] = []
        for root, client_label in scan_roots:
            for bundle_root in _manual_bundle_candidates(root):
                resolved = _safe_resolve(bundle_root)
                if resolved in seen:
                    continue
                seen.add(resolved)
                bundles.append(
                    self._plugin_bundle_from_path(
                        bundle_root,
                        publisher=bundle_root.parent.name,
                        name=bundle_root.name,
                        bundle_type="manual",
                        detected_client=client_label,
                    )
                )
        return bundles

    def load_registry(self) -> RegistryState:
        if not self.registry_path.is_file():
            return RegistryState(version=2, repos=[], plugins=[])

        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        version = int(data.get("version", 1))
        repos = [
            RepoRecord(
                owner=item["owner"],
                repo=item["repo"],
                repo_root=item["repo_root"],
                skills=list(item.get("skills", [])),
            )
            for item in data.get("repos", [])
        ]
        plugins = [
            PluginRecord(
                publisher=item["publisher"],
                name=item["name"],
                bundle_root=item["bundle_root"],
                manifest_type=item.get("manifest_type", "none"),
                exported_skills=list(item.get("exported_skills", [])),
                clients=dict(item.get("clients", {})),
            )
            for item in data.get("plugins", [])
        ]
        return RegistryState(version=version, repos=repos, plugins=plugins)

    def save_registry(self, state: RegistryState) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": state.version,
            "repos": [asdict(record) for record in state.repos],
            "plugins": [asdict(record) for record in state.plugins],
        }
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _invalid_skill_name_issue(self, skill_name: str, source_path: Path, client: str) -> AuditIssue:
        suggested = _suggest_client_safe_skill_name(skill_name, source_path)
        return AuditIssue(
            skill_name=skill_name,
            client=client,
            code="invalid_skill_name",
            message=(
                f"Skill frontmatter name is not compatible with {client}. "
                f"Allowed characters: {CLIENT_SAFE_SKILL_NAME_RULE}."
            ),
            path=source_path / "SKILL.md",
            proposed_action=(
                f"Rename `name:` to `{suggested}` or another client-safe identifier, "
                "then re-run align --apply."
            ),
        )

    def _invalid_skill_frontmatter_issue(
        self,
        skill_name: str,
        source_path: Path,
        client: str,
        error: str,
    ) -> AuditIssue:
        return AuditIssue(
            skill_name=skill_name,
            client=client,
            code="invalid_skill_frontmatter",
            message=f"Skill frontmatter is invalid: {error}",
            path=source_path / "SKILL.md",
            proposed_action=(
                "Fix the YAML frontmatter so it parses cleanly in every client, "
                "then re-run align --apply."
            ),
        )

    def _ensure_skill_frontmatter_is_valid(self, skill_dir: Path) -> None:
        error = _skill_frontmatter_error(skill_dir)
        if error is None:
            return
        raise RuntimeError(f"Invalid skill frontmatter in {skill_dir / 'SKILL.md'}: {error}")

    def _ensure_skill_set_frontmatter_is_valid(self, skill_dirs: dict[str, Path]) -> None:
        problems: list[str] = []
        for skill_name, skill_dir in sorted(skill_dirs.items()):
            error = _skill_frontmatter_error(skill_dir)
            if error is None:
                continue
            problems.append(f"{skill_name} -> {skill_dir / 'SKILL.md'} ({error})")
        if problems:
            raise RuntimeError("Cannot export skills with invalid frontmatter:\n- " + "\n- ".join(problems))

    def _ensure_skill_name_is_client_safe(self, skill_name: str, source_path: Path, clients: Iterable[str]) -> None:
        invalid_clients = [client for client in self._normalize_clients(clients) if not _is_client_safe_skill_name(skill_name)]
        if not invalid_clients:
            return

        suggested = _suggest_client_safe_skill_name(skill_name, source_path)
        client_list = ", ".join(invalid_clients)
        raise RuntimeError(
            f"Skill '{skill_name}' cannot be installed for {client_list}. "
            f"`name:` must contain only {CLIENT_SAFE_SKILL_NAME_RULE}. "
            f"Update {source_path / 'SKILL.md'} and consider `{suggested}`."
        )

    def _ensure_skill_set_is_client_safe(self, skill_dirs: dict[str, Path], clients: Iterable[str]) -> None:
        selected_clients = self._normalize_clients(clients)
        problems: list[str] = []
        for skill_name, skill_dir in sorted(skill_dirs.items()):
            invalid_clients = [client for client in selected_clients if not _is_client_safe_skill_name(skill_name)]
            if not invalid_clients:
                continue
            suggested = _suggest_client_safe_skill_name(skill_name, skill_dir)
            problems.append(
                f"{skill_name} [{', '.join(invalid_clients)}] -> rename `name:` in {skill_dir / 'SKILL.md'} to `{suggested}`"
            )
        if problems:
            raise RuntimeError(f"Cannot export client-incompatible skill names:\n- " + "\n- ".join(problems))

    def audit(self) -> AuditReport:
        sources = self.discover_sources()
        managed_bundles = self.discover_plugin_bundles()
        managed_bundle_targets = {_safe_resolve(bundle.path) for bundle in managed_bundles if bundle.bundle_type == "plugin-managed"}
        manual_bundles = [
            bundle
            for bundle in self._discover_manual_bundles()
            if _safe_resolve(bundle.path) not in managed_bundle_targets
        ]
        plugin_bundles = managed_bundles + manual_bundles
        client_skills = self._discover_client_skills()
        issues: list[AuditIssue] = []
        source_names_by_repo = self._source_names_by_repo(sources)

        for source in sources:
            issues.extend(self._audit_source(source, client_skills))

        for bundle in managed_bundles:
            skip_skill_names = self._hybrid_bundle_source_skill_names(bundle, source_names_by_repo)
            issues.extend(
                self._audit_plugin_bundle(
                    bundle,
                    client_skills,
                    skip_skill_names=skip_skill_names,
                    native_clients=self._native_installed_clients(bundle),
                )
            )

        for bundle in manual_bundles:
            issues.append(
                AuditIssue(
                    skill_name=bundle.name,
                    client=bundle.detected_client or "",
                    code="manual_bundle_detected",
                    message=f"Manual bundle detected outside managed roots: {bundle.path}",
                    path=bundle.path,
                    proposed_action="Normalize the bundle under ~/.skills/plugins before aligning clients.",
                )
            )

        expected_targets = self._expected_managed_client_targets(sources, managed_bundles)
        issue_paths = {
            issue.path
            for issue in issues
            if issue.path is not None and issue.code in {"broken_link", "legacy_copy", "target_mismatch"}
        }
        issues.extend(self._audit_stale_managed_exposures(client_skills, expected_targets, ignored_paths=issue_paths))

        classification_counts = dict(Counter(bundle.bundle_type for bundle in plugin_bundles))
        return AuditReport(
            sources=sources,
            plugin_bundles=plugin_bundles,
            client_skills=client_skills,
            issues=issues,
            classification_counts=classification_counts,
        )

    def _source_names_by_repo(self, sources: list[SkillSource]) -> dict[tuple[str | None, str | None], set[str]]:
        names_by_repo: dict[tuple[str | None, str | None], set[str]] = {}
        for source in sources:
            if source.source_type != "repo":
                continue
            names_by_repo.setdefault((source.owner, source.repo), set()).add(source.name)
        return names_by_repo

    def _hybrid_bundle_source_skill_names(
        self,
        bundle: PluginBundle,
        source_names_by_repo: dict[tuple[str | None, str | None], set[str]],
    ) -> set[str]:
        if bundle.bundle_type != "hybrid":
            return set()
        return source_names_by_repo.get((bundle.owner, bundle.repo), set())

    def _expected_managed_client_targets(
        self,
        sources: list[SkillSource],
        managed_bundles: list[PluginBundle],
    ) -> dict[str, set[Path]]:
        expected = {client: set() for client in CLIENT_NAMES}
        source_names_by_repo = self._source_names_by_repo(sources)
        for source in sources:
            client_paths = source.client_paths or {client: source.path for client in CLIENT_NAMES}
            for client, source_path in client_paths.items():
                expected[client].add(_safe_resolve(source_path))

        for bundle in managed_bundles:
            if bundle.bundle_type not in {"plugin-managed", "hybrid"}:
                continue
            skip_skill_names = self._hybrid_bundle_source_skill_names(bundle, source_names_by_repo)
            for skill_name, skill_dir in bundle.exported_skill_dirs.items():
                if skill_name in skip_skill_names:
                    continue
                target = _safe_resolve(skill_dir)
                for client in CLIENT_NAMES:
                    expected[client].add(target)
        return expected

    def _audit_stale_managed_exposures(
        self,
        client_skills: dict[str, list[ClientSkill]],
        expected_targets: dict[str, set[Path]],
        ignored_paths: set[Path] | None = None,
    ) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        ignored = ignored_paths or set()
        for client in CLIENT_NAMES:
            for item in client_skills.get(client, []):
                if item.top_entry in ignored or item.skill_dir in ignored:
                    continue
                if not item.direct or not item.top_entry_is_link:
                    continue
                target = item.resolved_skill_dir
                if not _is_relative_to(target, self.skills_root):
                    continue
                if target in expected_targets[client]:
                    continue
                issues.append(
                    AuditIssue(
                        skill_name=item.skill_name,
                        client=client,
                        code="stale_managed_exposure",
                        message="Client entry points into the managed tree, but no current managed source exports this skill.",
                        path=item.top_entry,
                        target=target,
                        proposed_action="Review and remove the stale link after confirming the source no longer exports it.",
                    )
                )
        return issues

    def _audit_source(self, source: SkillSource, client_skills: dict[str, list[ClientSkill]]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        client_paths = source.client_paths or {client: source.path for client in CLIENT_NAMES}

        for client in CLIENT_NAMES:
            source_path = client_paths.get(client)
            if source_path is None:
                continue
            source_target = _safe_resolve(source_path)
            frontmatter_error = _skill_frontmatter_error(source_path)
            if frontmatter_error:
                issues.append(self._invalid_skill_frontmatter_issue(source.name, source_path, client, frontmatter_error))
                continue
            if not _is_client_safe_skill_name(source.name):
                issues.append(self._invalid_skill_name_issue(source.name, source_path, client))
                continue
            matches = self._matching_client_entries(client_skills, client, source.name, source_path)
            exact = [item for item in matches if item.resolved_skill_dir == source_target]
            if exact:
                continue

            if matches:
                issues.append(
                    self._classify_misaligned_entries(
                        source.name,
                        client,
                        matches,
                        expected_target=source_path,
                        missing_code="missing_exposure",
                    )
                )
                continue

            issues.append(
                AuditIssue(
                    skill_name=source.name,
                    client=client,
                    code="missing_exposure",
                    message=f"Managed skill is not exposed in {client}.",
                    target=source_path,
                    proposed_action=f"Create link at {self._client_exposure_path(client, source.name, source_path)}.",
                )
            )

        return issues

    def _audit_plugin_bundle(
        self,
        bundle: PluginBundle,
        client_skills: dict[str, list[ClientSkill]],
        skip_skill_names: set[str] | None = None,
        native_clients: set[str] | None = None,
    ) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        skipped_names = skip_skill_names or set()
        native_covered_clients = native_clients or set()
        for skill_name, skill_dir in bundle.exported_skill_dirs.items():
            if skill_name in skipped_names:
                continue
            target = _safe_resolve(skill_dir)
            frontmatter_error = _skill_frontmatter_error(skill_dir)
            for client in CLIENT_NAMES:
                if client in native_covered_clients:
                    continue
                if frontmatter_error:
                    issues.append(self._invalid_skill_frontmatter_issue(skill_name, skill_dir, client, frontmatter_error))
                    continue
                if not _is_client_safe_skill_name(skill_name):
                    issues.append(self._invalid_skill_name_issue(skill_name, skill_dir, client))
                    continue
                matches = self._matching_client_entries(client_skills, client, skill_name, skill_dir)
                exact = [item for item in matches if item.resolved_skill_dir == target]
                if exact:
                    continue
                if matches:
                    issues.append(
                        self._classify_misaligned_entries(
                            skill_name,
                            client,
                            matches,
                            expected_target=skill_dir,
                            missing_code="missing_plugin_injection",
                        )
                    )
                    continue
                issues.append(
                    AuditIssue(
                        skill_name=skill_name,
                        client=client,
                        code="missing_plugin_injection",
                        message=f"Plugin-exported skill is not injected in {client}.",
                        target=skill_dir,
                        proposed_action=f"Create link at {self._client_exposure_path(client, skill_name, skill_dir)}.",
                    )
                )
        return issues

    def _native_installed_clients(self, bundle: PluginBundle) -> set[str]:
        if bundle.bundle_type not in {"plugin-managed", "hybrid"}:
            return set()
        if not self._has_native_plugin_surface(bundle.path):
            return set()

        plugin_name = self._native_plugin_name(bundle.path) or bundle.name
        installed: set[str] = set()
        for client in CLIENT_NAMES:
            cli = {"codex": "codex", "claude": "claude", "copilot": "copilot"}[client]
            cli_path = shutil.which(cli)
            if cli_path is None:
                continue
            for marketplace_name in self._native_marketplace_name_candidates(bundle, client, plugin_name):
                if self._native_plugin_installed(client, plugin_name, marketplace_name, cli_path=cli_path):
                    installed.add(client)
                    break
        return installed

    def _matching_client_entries(
        self,
        client_skills: dict[str, list[ClientSkill]],
        client: str,
        skill_name: str,
        expected_target: Path,
    ) -> list[ClientSkill]:
        expected_entry_name = self._client_exposure_path(client, skill_name, expected_target).name
        return [
            item
            for item in client_skills.get(client, [])
            if item.skill_name == skill_name or item.top_entry.name == expected_entry_name
        ]

    def _classify_misaligned_entries(
        self,
        skill_name: str,
        client: str,
        matches: list[ClientSkill],
        expected_target: Path,
        missing_code: str,
    ) -> AuditIssue:
        for item in matches:
            if item.top_entry_is_link and not item.skill_dir.exists():
                return AuditIssue(
                    skill_name=skill_name,
                    client=client,
                    code="broken_link",
                    message=f"Client entry points to a missing directory: {item.top_entry}",
                    path=item.top_entry,
                    target=expected_target,
                    proposed_action=f"Repair link to {expected_target}.",
                )

        for item in matches:
            if item.direct and not item.top_entry_is_link:
                return AuditIssue(
                    skill_name=skill_name,
                    client=client,
                    code="legacy_copy",
                    message=f"Client contains a standalone copy instead of a managed link: {item.skill_dir}",
                    path=item.skill_dir,
                    target=expected_target,
                    proposed_action="Replace the copy with a managed link after confirmation.",
                )

        item = matches[0]
        return AuditIssue(
            skill_name=skill_name,
            client=client,
            code="target_mismatch" if missing_code == "missing_exposure" else missing_code,
            message=f"Client entry resolves to {_safe_resolve(item.skill_dir)} instead of {expected_target}.",
            path=item.skill_dir,
            target=expected_target,
            proposed_action=f"Update the injection to point at {expected_target}.",
        )

    def _discover_client_skills(self) -> dict[str, list[ClientSkill]]:
        discovered: dict[str, list[ClientSkill]] = {}
        for client, root in self.client_roots().items():
            items: list[ClientSkill] = []
            if root.is_dir():
                for entry in sorted(root.iterdir()):
                    if not entry.is_dir() and not _path_exists_or_links(entry):
                        continue
                    top_entry_is_link = _is_link(entry)
                    top_entry_link_type = _link_type(entry)
                    direct_skill = entry / "SKILL.md"
                    if direct_skill.is_file():
                        items.append(
                            ClientSkill(
                                client=client,
                                skill_name=_read_skill_name(entry),
                                skill_dir=entry,
                                top_entry=entry,
                                direct=True,
                                top_entry_is_link=top_entry_is_link,
                                top_entry_link_type=top_entry_link_type,
                                resolved_skill_dir=_safe_resolve(entry),
                            )
                        )
                        continue
                    if top_entry_is_link and not entry.exists():
                        items.append(
                            ClientSkill(
                                client=client,
                                skill_name=entry.name,
                                skill_dir=entry,
                                top_entry=entry,
                                direct=True,
                                top_entry_is_link=top_entry_is_link,
                                top_entry_link_type=top_entry_link_type,
                                resolved_skill_dir=_safe_resolve(entry),
                            )
                        )
                        continue
                    for skill_md in sorted(entry.rglob("SKILL.md")):
                        skill_dir = skill_md.parent
                        items.append(
                            ClientSkill(
                                client=client,
                                skill_name=_read_skill_name(skill_dir),
                                skill_dir=skill_dir,
                                top_entry=entry,
                                direct=False,
                                top_entry_is_link=top_entry_is_link,
                                top_entry_link_type=top_entry_link_type,
                                resolved_skill_dir=_safe_resolve(skill_dir),
                            )
                        )
            discovered[client] = items
        return discovered

    def install_repo_skills(
        self,
        repo_slug: str,
        skill_paths: Iterable[str],
        clients: Iterable[str] | None = None,
        ref: str = "main",
        update_existing: bool = False,
    ) -> InstallResult:
        self.ensure_root_directories()
        client_list = self._normalize_clients(clients)
        owner, repo = self._parse_repo_slug(repo_slug)
        repo_root = self.repos_root / owner / repo
        if repo_root.exists():
            if update_existing and (repo_root / ".git").is_dir():
                _run_git(["git", "pull"], cwd=repo_root)
        else:
            repo_root.parent.mkdir(parents=True, exist_ok=True)
            _run_git(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    ref,
                    f"https://github.com/{owner}/{repo}.git",
                    str(repo_root),
                ]
            )

        installed: list[SkillSource] = []
        created_exposures: list[Path] = []
        skipped_exposures: list[Path] = []

        for skill_path in skill_paths:
            skill_dir = repo_root / skill_path
            if skill_dir.is_file() and skill_dir.name == "SKILL.md":
                skill_dir = skill_dir.parent
            if not (skill_dir / "SKILL.md").is_file():
                raise RuntimeError(f"Skill path does not contain SKILL.md: {skill_path}")

            self._ensure_skill_frontmatter_is_valid(skill_dir)
            source = SkillSource(
                name=_read_skill_name(skill_dir),
                path=skill_dir,
                source_type="repo",
                relative_path=skill_dir.relative_to(repo_root).as_posix(),
                owner=owner,
                repo=repo,
            )
            self._ensure_skill_name_is_client_safe(source.name, source.path, client_list)
            installed.append(source)
            for client in client_list:
                created, path_or_message = self._apply_skill_source_exposure(source, client)
                if created and isinstance(path_or_message, Path):
                    created_exposures.append(path_or_message)
                elif isinstance(path_or_message, Path):
                    skipped_exposures.append(path_or_message)

        registry = self.load_registry()
        updated_repos = [record for record in registry.repos if not (record.owner == owner and record.repo == repo)]
        updated_repos.append(
            RepoRecord(
                owner=owner,
                repo=repo,
                repo_root=str(repo_root),
                skills=[
                    {"name": source.name, "relative_path": source.relative_path}
                    for source in sorted(installed, key=lambda item: item.name)
                ],
            )
        )
        self.save_registry(RegistryState(version=max(registry.version, 2), repos=updated_repos, plugins=registry.plugins))

        return InstallResult(
            repo_root=repo_root,
            installed=installed,
            created_exposures=created_exposures,
            skipped_exposures=skipped_exposures,
        )

    def install_plugin_bundle(
        self,
        publisher: str,
        name: str,
        source_root: Path | None = None,
        repo_slug: str | None = None,
        clients: Iterable[str] | None = None,
        ref: str = "main",
        update_existing: bool = False,
        export_skills: Iterable[str] | None = None,
        native: bool = False,
        native_dry_run: bool = False,
        native_marketplace_source: str | None = None,
        native_marketplace_name: str | None = None,
        native_plugin_name: str | None = None,
        native_plugin_source: str | None = None,
    ) -> PluginInstallResult:
        self.ensure_root_directories()
        client_list = self._normalize_clients(clients)
        bundle_root = self.plugins_root / publisher / name
        notes: list[str] = []

        if bool(source_root) == bool(repo_slug):
            raise RuntimeError("Specify exactly one of source_root or repo_slug.")

        owner: str | None = None
        repo: str | None = None
        if native_dry_run:
            if source_root:
                bundle_path = source_root
                notes.append(f"Dry run only: would link plugin bundle at {bundle_root}.")
            else:
                owner, repo = self._parse_repo_slug(repo_slug or "")
                bundle_path = bundle_root
                if bundle_root.exists():
                    if update_existing and (bundle_root / ".git").is_dir():
                        notes.append(f"Dry run only: would update existing plugin bundle at {bundle_root}.")
                    else:
                        notes.append(f"Plugin bundle already present: {bundle_root}")
                else:
                    notes.append(
                        f"Dry run only: would clone https://github.com/{owner}/{repo}.git "
                        f"at ref {ref} into {bundle_root}."
                    )

            if not bundle_path.exists():
                bundle = PluginBundle(
                    publisher=publisher,
                    name=name,
                    path=bundle_path,
                    bundle_type="plugin-managed",
                    manifest_type="none",
                    owner=owner,
                    repo=repo,
                )
                native_notes = [
                    "Native plugin dry-run skipped: bundle is not present locally, "
                    "so manifests cannot be inspected without cloning."
                ]
            else:
                bundle = self._plugin_bundle_from_path(
                    bundle_path,
                    publisher=publisher,
                    name=name,
                    bundle_type="plugin-managed",
                    owner=owner,
                    repo=repo,
                    export_skills=list(export_skills) if export_skills else None,
                )
                self._ensure_skill_set_frontmatter_is_valid(bundle.exported_skill_dirs)
                self._ensure_skill_set_is_client_safe(bundle.exported_skill_dirs, client_list)
                native_notes = (
                    self._apply_native_plugin_installs(
                        bundle,
                        client_list,
                        dry_run=True,
                        marketplace_path=bundle_root,
                        marketplace_source=native_marketplace_source,
                        marketplace_name=native_marketplace_name,
                        plugin_name=native_plugin_name,
                        direct_plugin_source=native_plugin_source,
                    )
                    if native
                    else []
                )

            if not bundle.exported_skills:
                notes.append(f"No exported skills found under {bundle_path / 'skills'}.")

            return PluginInstallResult(
                bundle_root=bundle_root,
                bundle=bundle,
                created_exposures=[],
                skipped_exposures=[],
                notes=notes,
                native_notes=native_notes,
            )

        if source_root:
            created, message = _ensure_directory_link(bundle_root, source_root)
            if not created:
                notes.append(message)
        else:
            owner, repo = self._parse_repo_slug(repo_slug or "")
            if bundle_root.exists():
                if update_existing and (bundle_root / ".git").is_dir():
                    _run_git(["git", "pull"], cwd=bundle_root)
                else:
                    notes.append(f"Plugin bundle already present: {bundle_root}")
            else:
                bundle_root.parent.mkdir(parents=True, exist_ok=True)
                _run_git(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        "--branch",
                        ref,
                        f"https://github.com/{owner}/{repo}.git",
                        str(bundle_root),
                    ]
                )

        bundle = self._plugin_bundle_from_path(
            bundle_root,
            publisher=publisher,
            name=name,
            bundle_type="plugin-managed",
            owner=owner,
            repo=repo,
            export_skills=list(export_skills) if export_skills else None,
        )
        self._ensure_skill_set_frontmatter_is_valid(bundle.exported_skill_dirs)
        self._ensure_skill_set_is_client_safe(bundle.exported_skill_dirs, client_list)
        created_exposures, skipped_exposures = self._apply_exported_skill_exposures(bundle, client_list)
        native_notes = (
            self._apply_native_plugin_installs(
                bundle,
                client_list,
                dry_run=native_dry_run,
                marketplace_source=native_marketplace_source,
                marketplace_name=native_marketplace_name,
                plugin_name=native_plugin_name,
                direct_plugin_source=native_plugin_source,
            )
            if native
            else []
        )

        registry = self.load_registry()
        updated_plugins = [
            record
            for record in registry.plugins
            if not (record.publisher == publisher and record.name == name)
        ]
        updated_plugins.append(
            PluginRecord(
                publisher=publisher,
                name=name,
                bundle_root=str(bundle_root),
                manifest_type=bundle.manifest_type,
                exported_skills=bundle.exported_skills,
                clients={client: "exported-skills" for client in client_list},
            )
        )
        self.save_registry(RegistryState(version=max(registry.version, 2), repos=registry.repos, plugins=updated_plugins))

        if not bundle.exported_skills:
            notes.append(f"No exported skills found under {bundle_root / 'skills'}.")

        return PluginInstallResult(
            bundle_root=bundle_root,
            bundle=bundle,
            created_exposures=created_exposures,
            skipped_exposures=skipped_exposures,
            notes=notes,
            native_notes=native_notes,
        )

    def _apply_native_plugin_installs(
        self,
        bundle: PluginBundle,
        clients: Iterable[str],
        dry_run: bool = False,
        marketplace_path: Path | None = None,
        marketplace_source: str | None = None,
        marketplace_name: str | None = None,
        plugin_name: str | None = None,
        direct_plugin_source: str | None = None,
    ) -> list[str]:
        notes: list[str] = []
        if not self._has_native_plugin_surface(bundle.path):
            return [f"Native plugin install skipped: no client plugin manifests found in {bundle.path}."]

        resolved_plugin_name = plugin_name or self._native_plugin_name(bundle.path) or bundle.name
        marketplace_root = marketplace_path or bundle.path
        marketplace_source_value = marketplace_source or str(marketplace_root)
        for client in self._normalize_clients(clients):
            if not self._has_native_plugin_surface_for_client(bundle.path, client):
                notes.append(f"Native [{client}]: skipped, no compatible native plugin manifest found in {bundle.path}.")
                continue

            cli = {"codex": "codex", "claude": "claude", "copilot": "copilot"}[client]
            cli_path = shutil.which(cli)
            if cli_path is None:
                notes.append(f"Native [{client}]: skipped, `{cli}` CLI not found in PATH.")
                continue

            resolved_marketplace_name = marketplace_name or self._native_marketplace_name(bundle.path, client) or bundle.publisher
            selector = f"{resolved_plugin_name}@{resolved_marketplace_name}"
            use_direct_install = client == "copilot" and bool(direct_plugin_source)
            marketplace_add = [cli_path, "plugin", "marketplace", "add", marketplace_source_value]
            action = (
                "install"
                if dry_run
                else (
                    "update"
                    if self._native_plugin_installed(client, resolved_plugin_name, resolved_marketplace_name, cli_path=cli_path)
                    else "install"
                )
            )
            action_command = self._native_plugin_action_command(
                client,
                selector,
                resolved_plugin_name,
                action,
                cli_path=cli_path,
                direct_source=direct_plugin_source if use_direct_install else None,
            )
            commands = [action_command] if use_direct_install else [marketplace_add, action_command]
            display_commands = [[cli, *command[1:]] for command in commands]

            if dry_run:
                notes.append(f"Native [{client}] dry-run: " + " && ".join(_format_command(command) for command in display_commands))
                continue

            marketplace_registered = self._native_marketplace_registered(client, resolved_marketplace_name, cli_path=cli_path)
            add_status: str
            if use_direct_install:
                add_status = "not-used"
            elif marketplace_registered:
                add_status = "skipped"
            else:
                add_status = str(_run_inherited(marketplace_add))
            action_code = _run_inherited(action_command)
            installed_after = self._native_plugin_installed(client, resolved_plugin_name, resolved_marketplace_name, cli_path=cli_path)
            if installed_after:
                notes.append(
                    f"Native [{client}]: {action} verified for {selector} "
                    f"(marketplace add {add_status}, {action} exit {action_code})."
                )
            else:
                notes.append(
                    f"Native [{client}]: {action} not verified for {selector} "
                    f"(marketplace add {add_status}, {action} exit {action_code})."
                )
        return notes

    def _has_native_plugin_surface(self, bundle_root: Path) -> bool:
        return any(
            path.is_file()
            for path in [
                bundle_root / ".claude-plugin" / "plugin.json",
                bundle_root / ".codex-plugin" / "plugin.json",
                bundle_root / "plugin" / ".claude-plugin" / "plugin.json",
                bundle_root / "plugin" / ".codex-plugin" / "plugin.json",
            ]
        )

    def _has_native_plugin_surface_for_client(self, bundle_root: Path, client: str) -> bool:
        claude_manifests = [
            bundle_root / ".claude-plugin" / "plugin.json",
            bundle_root / "plugin" / ".claude-plugin" / "plugin.json",
        ]
        if client == "claude":
            return any(path.is_file() for path in claude_manifests)
        if client == "codex":
            return any(
                path.is_file()
                for path in [
                    bundle_root / ".codex-plugin" / "plugin.json",
                    bundle_root / "plugin" / ".codex-plugin" / "plugin.json",
                ]
            )
        if client == "copilot":
            return any(
                path.is_file()
                for path in [
                    bundle_root / ".copilot-plugin" / "plugin.json",
                    bundle_root / "plugin" / ".copilot-plugin" / "plugin.json",
                    *claude_manifests,
                ]
            )
        return False

    def _native_plugin_name(self, bundle_root: Path) -> str | None:
        for path in [
            bundle_root / ".claude-plugin" / "plugin.json",
            bundle_root / ".codex-plugin" / "plugin.json",
            bundle_root / "plugin" / ".claude-plugin" / "plugin.json",
            bundle_root / "plugin" / ".codex-plugin" / "plugin.json",
        ]:
            payload = _read_json_if_exists(path)
            if payload and payload.get("name"):
                return str(payload["name"])
        return None

    def _native_marketplace_name(self, bundle_root: Path, client: str) -> str | None:
        candidates = []
        if client == "codex":
            candidates.append(bundle_root / ".agents" / "plugins" / "marketplace.json")
            candidates.append(bundle_root / "agents" / "plugins" / "marketplace.json")
        candidates.extend(
            [
                bundle_root / ".claude-plugin" / "marketplace.json",
                bundle_root / "marketplace.json",
            ]
        )
        for path in candidates:
            payload = _read_json_if_exists(path)
            if payload and payload.get("name"):
                return str(payload["name"])
        return None

    def _native_marketplace_name_candidates(self, bundle: PluginBundle, client: str, plugin_name: str) -> list[str]:
        candidates = [
            self._native_marketplace_name(bundle.path, client),
            bundle.publisher,
            f"{plugin_name}-skills",
            f"{bundle.name}-skills",
        ]
        unique: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            if candidate not in unique:
                unique.append(candidate)
        return unique

    def _native_plugin_action_command(
        self,
        client: str,
        selector: str,
        plugin_name: str,
        action: str,
        cli_path: str | None = None,
        direct_source: str | None = None,
    ) -> list[str]:
        if client == "codex":
            return [cli_path or "codex", "plugin", "add", selector]
        if client == "copilot":
            if direct_source and action == "install":
                return [cli_path or "copilot", "plugin", "install", direct_source]
            if direct_source and action == "update":
                return [cli_path or "copilot", "plugin", "update", plugin_name]
            return [cli_path or "copilot", "plugin", "update" if action == "update" else "install", selector]
        return [cli_path or "claude", "plugin", "update" if action == "update" else "install", selector]

    def _native_plugin_installed(self, client: str, plugin_name: str, marketplace_name: str, cli_path: str | None = None) -> bool:
        if client == "codex":
            ok, output = self._native_plugin_list_output(client, cli_path=cli_path)
            if not ok:
                return False
            try:
                payload = json.loads(output or "{}")
            except json.JSONDecodeError:
                return False
            return self._json_plugin_list_contains(payload, plugin_name, marketplace_name)

        if client == "claude":
            ok, output = self._native_plugin_list_output(client, cli_path=cli_path)
            if not ok:
                return False
            try:
                payload = json.loads(output or "[]")
            except json.JSONDecodeError:
                return plugin_name.lower() in output.lower()
            return self._json_plugin_list_contains(payload, plugin_name, marketplace_name)

        ok, output = self._native_plugin_list_output(client, cli_path=cli_path)
        return ok and plugin_name.lower() in output.lower()

    def _native_plugin_list_output(
        self,
        client: str,
        cli_path: str | None = None,
        marketplace_name: str | None = None,
    ) -> tuple[bool, str]:
        cache_key = (client, cli_path or "", marketplace_name or "")
        if cache_key in self._native_plugin_list_cache:
            return self._native_plugin_list_cache[cache_key]

        if client == "codex":
            command = [cli_path or "codex", "plugin", "list", "--json"]
        elif client == "claude":
            command = [cli_path or "claude", "plugin", "list", "--json"]
        else:
            command = [cli_path or "copilot", "plugin", "list"]

        result = _run_captured(command, timeout=30)
        self._native_plugin_list_cache[cache_key] = result
        return result

    def _native_marketplace_registered(self, client: str, marketplace_name: str, cli_path: str | None = None) -> bool:
        cli = {"codex": "codex", "claude": "claude", "copilot": "copilot"}[client]
        ok, output = _run_captured([cli_path or cli, "plugin", "marketplace", "list"], timeout=30)
        return ok and marketplace_name.lower() in output.lower()

    def _json_plugin_list_contains(self, payload: object, plugin_name: str, marketplace_name: str) -> bool:
        if isinstance(payload, dict):
            candidates: list[object] = []
            for key in ["installed", "plugins", "items"]:
                value = payload.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
            if not candidates and payload:
                candidates.append(payload)
        elif isinstance(payload, list):
            candidates = list(payload)
        else:
            return False

        for item in candidates:
            if not isinstance(item, dict):
                continue
            values = {str(value).lower() for value in item.values() if isinstance(value, str)}
            if plugin_name.lower() in values or f"{plugin_name}@{marketplace_name}".lower() in values:
                return True
        return False

    def _plugin_bundle_from_path(
        self,
        bundle_root: Path,
        publisher: str,
        name: str,
        bundle_type: str,
        owner: str | None = None,
        repo: str | None = None,
        detected_client: str | None = None,
        export_skills: list[str] | None = None,
    ) -> PluginBundle:
        if not _plugin_like_structure(bundle_root):
            raise RuntimeError(f"Path is not a recognized plugin bundle: {bundle_root}")
        exported_skill_dirs = _exported_skill_dirs(bundle_root)
        if export_skills:
            requested = set(export_skills)
            missing = sorted(requested - set(exported_skill_dirs))
            if missing:
                raise RuntimeError(f"Requested exported skills not found: {', '.join(missing)}")
            exported_skill_dirs = {
                skill_name: exported_skill_dirs[skill_name]
                for skill_name in sorted(exported_skill_dirs)
                if skill_name in requested
            }
        return PluginBundle(
            publisher=publisher,
            name=name,
            path=bundle_root,
            bundle_type=bundle_type,
            manifest_type=_plugin_manifest_type(bundle_root),
            exported_skills=sorted(exported_skill_dirs),
            exported_skill_dirs=exported_skill_dirs,
            owner=owner,
            repo=repo,
            detected_client=detected_client,
        )

    def _apply_exported_skill_exposures(
        self,
        bundle: PluginBundle,
        clients: Iterable[str] | None = None,
    ) -> tuple[list[Path], list[Path]]:
        client_list = self._normalize_clients(clients)
        created: list[Path] = []
        skipped: list[Path] = []
        for client in client_list:
            for skill_name, skill_dir in bundle.exported_skill_dirs.items():
                destination = self._client_exposure_path(client, skill_name, skill_dir)
                created_link, _ = _ensure_directory_link(destination, skill_dir, replace_existing_link=True)
                if created_link:
                    created.append(destination)
                else:
                    skipped.append(destination)
        return created, skipped

    def update_repos(self, repo_slug: str | None = None) -> list[UpdateResult]:
        registry = self.load_registry()
        requested_repo = repo_slug.lower() if repo_slug else None
        seen: set[Path] = set()
        candidates: list[Path] = []

        for record in registry.repos:
            label = f"{record.owner}/{record.repo}".lower()
            if requested_repo and label != requested_repo:
                continue
            root = Path(record.repo_root)
            if root not in seen and (root / ".git").is_dir():
                seen.add(root)
                candidates.append(root)

        for record in registry.plugins:
            label = f"{record.publisher}/{record.name}".lower()
            if requested_repo and label != requested_repo:
                continue
            root = Path(record.bundle_root)
            if root not in seen and (root / ".git").is_dir():
                seen.add(root)
                candidates.append(root)

        results: list[UpdateResult] = []
        for root in candidates:
            try:
                output = _run_git(["git", "pull"], cwd=root)
                results.append(UpdateResult(repo_root=root, success=True, output=output))
            except Exception as exc:  # pragma: no cover - defensive surface
                results.append(UpdateResult(repo_root=root, success=False, output=str(exc)))
        return results

    def align(self, apply: bool = False) -> tuple[AuditReport, list[str]]:
        report = self.audit()
        if not apply:
            return report, []

        self.ensure_root_directories()
        source_map = {source.name: source.path for source in report.sources}
        plugin_skill_map: dict[str, Path] = {}
        for bundle in report.plugin_bundles:
            if bundle.bundle_type not in {"plugin-managed", "hybrid"}:
                continue
            plugin_skill_map.update(bundle.exported_skill_dirs)

        actions: list[str] = []
        for issue in sorted(report.issues, key=lambda item: (item.skill_name, item.client, item.code)):
            if issue.code == "missing_exposure":
                target = issue.target or source_map.get(issue.skill_name)
                if not target or not issue.client:
                    continue
                path = self._client_exposure_path(issue.client, issue.skill_name, target)
                created, message = _ensure_directory_link(path, target)
                action = f"{'Created' if created else 'Skipped'} skill link for {issue.skill_name} in {issue.client}: {path}"
                if not created and message:
                    action = f"{action} ({message})"
                actions.append(action)
            elif issue.code == "missing_plugin_injection":
                target = plugin_skill_map.get(issue.skill_name)
                if not target or not issue.client:
                    continue
                path = self._client_exposure_path(issue.client, issue.skill_name, target)
                created, message = _ensure_directory_link(path, target)
                action = f"{'Created' if created else 'Skipped'} plugin injection for {issue.skill_name} in {issue.client}: {path}"
                if not created and message:
                    action = f"{action} ({message})"
                actions.append(action)
            elif issue.code == "broken_link":
                if not issue.path or not issue.target or not issue.client:
                    continue
                try:
                    if _is_link(issue.path):
                        issue.path.unlink()
                except OSError as exc:
                    actions.append(f"Failed to remove broken link {issue.path}: {exc}")
                    continue
                try:
                    created, message = _ensure_directory_link(issue.path, issue.target)
                except RuntimeError as exc:
                    actions.append(f"Failed to repair link for {issue.skill_name} in {issue.client}: {exc}")
                    continue
                action = f"Repaired broken link for {issue.skill_name} in {issue.client}: {issue.path} -> {issue.target}"
                if not created and message:
                    action = f"{action} ({message})"
                actions.append(action)
            elif issue.code == "target_mismatch":
                if not issue.path or not issue.target or not issue.client:
                    continue
                if not _is_link(issue.path):
                    actions.append(
                        f"Manual action required - target mismatch for {issue.skill_name} in {issue.client}: "
                        f"{issue.path} is not a managed link; inspect before replacing it with {issue.target}."
                    )
                    continue
                try:
                    created, message = _ensure_directory_link(issue.path, issue.target, replace_existing_link=True)
                except RuntimeError as exc:
                    actions.append(f"Failed to update link for {issue.skill_name} in {issue.client}: {exc}")
                    continue
                action = f"{'Updated' if created else 'Skipped'} skill link target for {issue.skill_name} in {issue.client}: {issue.path}"
                if message:
                    action = f"{action} ({message})"
                actions.append(action)
            elif issue.code == "legacy_copy":
                if not issue.path or not issue.target or not issue.client:
                    continue
                actions.append(
                    f"Manual action required - standalone copy found for {issue.skill_name} in {issue.client}: "
                    f"inspect, backup, and compare {issue.path} against the managed target {issue.target}, "
                    f"then remove or migrate the standalone copy and re-run align to create the managed link."
                )
            elif issue.code == "invalid_skill_name":
                if not issue.path or not issue.client:
                    continue
                actions.append(
                    f"Manual action required - incompatible skill name for {issue.skill_name} in {issue.client}: "
                    f"update {issue.path} so `name:` uses only {CLIENT_SAFE_SKILL_NAME_RULE}, "
                    "then re-run align --apply."
                )
            elif issue.code == "invalid_skill_frontmatter":
                if not issue.path or not issue.client:
                    continue
                actions.append(
                    f"Manual action required - invalid frontmatter for {issue.skill_name} in {issue.client}: "
                    f"fix {issue.path}, then re-run align --apply."
                )
            elif issue.code == "stale_managed_exposure":
                if not issue.path or not issue.target or not issue.client:
                    continue
                actions.append(
                    f"Manual action required - stale managed link for {issue.skill_name} in {issue.client}: "
                    f"{issue.path} points at {issue.target}, but no current managed source exports it. "
                    "Remove the link after confirming it is obsolete."
                )

        return self.audit(), actions

    def _apply_skill_source_exposure(self, source: SkillSource, client: str) -> tuple[bool, Path | str]:
        client_root = self.client_roots()[client]
        if client == "codex" and _is_relative_to(source.path, self.custom_root):
            aggregate = client_root / "custom"
            if _path_exists_or_links(aggregate) and _safe_resolve(aggregate) == _safe_resolve(self.custom_root):
                return False, f"Skipped {source.name}: existing Codex custom aggregate already exposes managed custom skills."
        destination = self._client_exposure_path(client, source.name, source.path)
        created, _ = _ensure_directory_link(destination, source.path)
        return created, destination

    def _client_exposure_path(self, client: str, skill_name: str, source_path: Path) -> Path:
        return self.client_roots()[client] / _exposure_dir_name(skill_name, source_path)

    def _normalize_clients(self, clients: Iterable[str] | None) -> list[str]:
        if not clients:
            return list(CLIENT_NAMES)
        normalized: list[str] = []
        for client in clients:
            if client not in CLIENT_NAMES:
                raise RuntimeError(f"Unsupported client: {client}")
            if client not in normalized:
                normalized.append(client)
        return normalized

    def _policy_paths_for_clients(self, clients: Iterable[str]) -> dict[str, Path]:
        selected = self._normalize_clients(clients)
        return {
            client: {
                "codex": self.home / ".codex" / "AGENTS.override.md",
                "claude": self.home / ".claude" / "CLAUDE.md",
                "copilot": self.home / ".copilot" / "copilot-instructions.md",
            }[client]
            for client in selected
        }

    def _policy_block(self, client: str) -> str:
        return "\n".join(
            [
                "## Skill Management Policy",
                "Prefer `skill-install-plus-plus` for skill installation, audit, alignment, update, and uninstall tasks.",
                "Treat `~/.skills` as the source of truth.",
                "- GitHub-backed skills live in `~/.skills/repos/<owner>/<repo>`.",
                "- Personal skills live in `~/.skills/custom`.",
                "- Plugin bundles live in `~/.skills/plugins/<publisher>/<name>`.",
                "- Expose skills and plugin-exported skills into client discovery directories using links, not standalone copies.",
                f"- This policy is active for `{client}`.",
            ]
        )

    def _parse_repo_slug(self, repo_slug: str) -> tuple[str, str]:
        parts = [item for item in repo_slug.strip().split("/") if item]
        if len(parts) != 2:
            raise RuntimeError(f"Invalid repo slug: {repo_slug}")
        return parts[0], parts[1]
