#!/usr/bin/env node
/**
 * Guardrail for the Node installer surface.
 *
 * The installer version lives in package.json. The managed source version lives
 * in plugin manifests when this repo is a plugin bundle, otherwise in
 * pyproject.toml for the Python skillpp package. These versions intentionally
 * do not have to match.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const errors = [];

const read = (rel) => readFileSync(path.join(ROOT, rel), 'utf8');
const readJson = (rel) => JSON.parse(read(rel));
const exists = (rel) => existsSync(path.join(ROOT, rel));

const pkg = readJson('package.json');
if (pkg.type !== 'module') errors.push('package.json must set "type": "module"');
if (pkg.bin?.['skillpp-install'] !== './install.mjs') {
  errors.push('package.json must expose bin skillpp-install -> ./install.mjs');
}
for (const dep of ['@clack/prompts', 'picocolors']) {
  if (!pkg.dependencies?.[dep]) errors.push(`package.json is missing dependency ${dep}`);
}
for (const script of ['start', 'check', 'test']) {
  if (!pkg.scripts?.[script]) errors.push(`package.json is missing script ${script}`);
}

const installer = read('install.mjs');
for (const required of [
  '@clack/prompts',
  'picocolors',
  'spawnSync',
  "stdio: 'inherit'",
  '--status',
  '--dry-run',
  '--yes',
]) {
  if (!installer.includes(required)) errors.push(`install.mjs missing required surface: ${required}`);
}

const claudeManifest = exists('.claude-plugin/plugin.json') ? readJson('.claude-plugin/plugin.json') : null;
const codexManifest = exists('.codex-plugin/plugin.json') ? readJson('.codex-plugin/plugin.json') : null;
if (claudeManifest || codexManifest) {
  if (!claudeManifest) errors.push('plugin mode requires .claude-plugin/plugin.json');
  if (!codexManifest) errors.push('plugin mode requires .codex-plugin/plugin.json');
  if (claudeManifest && codexManifest && claudeManifest.version !== codexManifest.version) {
    errors.push(
      `.claude-plugin/plugin.json (${claudeManifest.version}) and ` +
        `.codex-plugin/plugin.json (${codexManifest.version}) versions diverge`,
    );
  }
  if (exists('.claude-plugin/marketplace.json')) {
    const market = readJson('.claude-plugin/marketplace.json');
    const marketPlugin = (market.plugins ?? []).find((item) => item.name === claudeManifest?.name);
    if (marketPlugin?.version) {
      errors.push('.claude-plugin/marketplace.json must not duplicate plugin version');
    }
  }
} else {
  const skill = read('SKILL.md');
  const pyproject = read('pyproject.toml');
  if (!/^name:\s*skill-install-plus-plus/m.test(skill)) {
    errors.push('SKILL.md must declare name: skill-install-plus-plus');
  }
  if (!/^version\s*=\s*"[^"]+"/m.test(pyproject)) {
    errors.push('pyproject.toml must declare the managed source version');
  }
}

const help = spawnSync('node install.mjs --help', {
  cwd: ROOT,
  shell: true,
  encoding: 'utf8',
  timeout: 30000,
});
if (help.status !== 0) {
  errors.push(`node install.mjs --help failed: ${help.stdout}${help.stderr}`);
} else if (!help.stdout.includes('--status') || !help.stdout.includes('--dry-run')) {
  errors.push('node install.mjs --help does not document required flags');
}

if (errors.length) {
  console.error('Installer check FAILED:');
  for (const error of errors) console.error(`  - ${error}`);
  process.exit(1);
}

console.log(`Installer check OK - installer ${pkg.version}; source version is managed separately.`);
