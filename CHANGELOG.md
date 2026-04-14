# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic
Versioning.

## [Unreleased]

### Changed

## [0.1.2] - 2026-04-14

### Changed

- Expanded Windows CI coverage to Python 3.10, 3.11, 3.12, and 3.13 while
  keeping packaging validation in the test workflow
- Added stronger automated regression coverage for CLI align behavior,
  repository install clone and pull branches, and manual plugin bundle
  discovery across client roots

### Fixed

- Repaired `align --apply` so it now fixes `broken_link` issues instead of
  silently skipping them
- Kept `legacy_copy` handling non-destructive and improved the guidance so
  users inspect, back up, compare, and then migrate or remove standalone
  copies before re-running align
- Fixed broken-link repair for Windows-unsafe skill names that are exposed via
  fallback directory names, such as `ckm:banner-design -> banner-design`
- Extended manual plugin bundle discovery to detect unmanaged bundles under
  `~/.agents` and `~/.claude` in addition to `~/.codex`
- Removed the CLI metadata test dependency on `tomllib` or `tomli` so the test
  suite stays compatible with Python 3.10

## [0.1.1] - 2026-04-13

### Changed

- Refined the public README with a stronger hero, clearer workflow copy, and an
  ASCII-safe source-of-truth example for GitHub and PyPI rendering
- Added aligned light and dark `skillpp` wordmark SVG assets with the new
  two-tone `++` treatment
- Updated GitHub Actions references to Node 24-compatible action versions

### Fixed

- Normalized client exposure directory names on Windows when a skill name
  contains characters that are invalid for directory creation

## [0.1.0] - 2026-04-13

### Added

- Initial public packaging for `skillpp`
- Public CLI entry point `skillpp`
- MIT license and community health files
- GitHub Actions workflows for CI and PyPI-ready release automation
