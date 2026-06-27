#!/usr/bin/env node
/**
 * Interactive installer for the current skill/plugin source.
 *
 * Modes:
 * - plugin mode: if plugin manifests exist, use native client plugin commands.
 * - skill mode: otherwise bootstrap this repository as a managed skill through
 *   the existing Python `skillpp` CLI and verify client discovery roots.
 */
import { spawnSync } from 'node:child_process';
import {
  existsSync,
  lstatSync,
  readFileSync,
  realpathSync,
} from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CLIENTS = ['claude', 'codex', 'copilot'];
const CLIENT_ROOTS = {
  claude: ['.claude', 'skills'],
  codex: ['.agents', 'skills'],
  copilot: ['.copilot', 'skills'],
};
const CLIENT_LABELS = {
  claude: 'Claude Code',
  codex: 'Codex',
  copilot: 'GitHub Copilot CLI',
};
const CLIENT_CLIS = {
  claude: 'claude',
  codex: 'codex',
  copilot: 'copilot',
};

const argv = parseArgs(process.argv.slice(2));
if (argv.help) {
  printHelp();
  process.exit(0);
}

const q = (value) => `"${String(value).replaceAll('"', '\\"')}"`;
const source = readSource(REPO_ROOT);
const ui = await loadUi();
const pc = ui.pc;

async function main() {
  ui.intro(`${pc.bgCyan(pc.black(' skillpp installer '))}${argv.dryRun ? pc.yellow(' [dry-run]') : ''}`);
  ui.log.message(
    `${source.kind === 'plugin' ? 'Plugin' : 'Skill'} ${pc.bold(source.name)} ` +
      `v${pc.bold(source.version ?? '?')} ` +
      `${source.marketplace ? `marketplace ${pc.bold(source.marketplace)} ` : ''}` +
      pc.dim(REPO_ROOT),
  );

  const spinner = ui.spinner();
  spinner.start('Detecting client state');
  const states = DEFAULT_CLIENTS.map((client) => detectClient(client, source));
  spinner.stop('Client state detected');
  ui.note(renderStates(states), 'Status');

  if (argv.status) {
    ui.outro('Status only; no changes made.');
    return;
  }

  const selected = await chooseClients(states);
  if (selected.length === 0) {
    ui.cancel('No clients selected.');
    process.exit(0);
  }

  if (!argv.yes) {
    const proceed = await ui.confirm({
      message: `Proceed on ${selected.map((key) => CLIENT_LABELS[key]).join(', ')}?`,
    });
    if (ui.isCancel(proceed) || !proceed) {
      ui.cancel('Cancelled.');
      process.exit(0);
    }
  }

  const results = [];
  for (const client of selected) {
    const state = states.find((item) => item.key === client);
    ui.log.step(pc.bold(CLIENT_LABELS[client]));
    results.push(await applyClient(client, source, state));
  }

  ui.note(
    results.map((item) => `${item.ok ? pc.green('OK') : pc.red('FAIL')} ${item.label}`).join('\n'),
    'Result',
  );
  const failures = results.filter((item) => !item.ok).length;
  ui.outro(failures === 0 ? pc.green('Done.') : pc.yellow(`Completed with ${failures} problem(s).`));
  if (failures) process.exitCode = 1;
}

function parseArgs(items) {
  const parsed = {
    clients: [],
    dryRun: false,
    help: false,
    status: false,
    yes: false,
  };

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (item === '--help' || item === '-h') parsed.help = true;
    else if (item === '--status' || item === '-s') parsed.status = true;
    else if (item === '--dry-run' || item === '-n') parsed.dryRun = true;
    else if (item === '--yes' || item === '-y') parsed.yes = true;
    else if (item === '--client') {
      const value = items[index + 1];
      if (!value) throw new Error('--client requires claude, codex, or copilot');
      parsed.clients.push(normalizeClient(value));
      index += 1;
    } else if (item.startsWith('--client=')) {
      parsed.clients.push(normalizeClient(item.slice('--client='.length)));
    } else {
      throw new Error(`Unknown argument: ${item}`);
    }
  }
  parsed.clients = [...new Set(parsed.clients)];
  return parsed;
}

function normalizeClient(value) {
  const normalized = String(value).toLowerCase();
  if (!DEFAULT_CLIENTS.includes(normalized)) {
    throw new Error(`Unsupported client: ${value}`);
  }
  return normalized;
}

function readSource(root) {
  const claudeManifest = readJsonIfExists(path.join(root, '.claude-plugin', 'plugin.json'));
  const codexManifest = readJsonIfExists(path.join(root, '.codex-plugin', 'plugin.json'));
  if (claudeManifest || codexManifest) {
    const manifest = claudeManifest ?? codexManifest;
    const marketplace =
      readJsonIfExists(path.join(root, '.claude-plugin', 'marketplace.json'))?.name ??
      readJsonIfExists(path.join(root, '.agents', 'plugins', 'marketplace.json'))?.name ??
      `${manifest.name}-skills`;
    return {
      kind: 'plugin',
      name: manifest.name,
      version: manifest.version ?? codexManifest?.version ?? null,
      marketplace,
    };
  }

  const skillPath = path.join(root, 'SKILL.md');
  if (!existsSync(skillPath)) {
    throw new Error(`No plugin manifest or SKILL.md found at ${root}`);
  }
  return {
    kind: 'skill',
    name: readSkillName(skillPath),
    version: readPyprojectVersion(root) ?? readPackageVersion(root),
    marketplace: null,
  };
}

function readJsonIfExists(filePath) {
  if (!existsSync(filePath)) return null;
  return JSON.parse(readFileSync(filePath, 'utf8'));
}

function readSkillName(skillPath) {
  const text = readFileSync(skillPath, 'utf8');
  const match = text.match(/^name:\s*['"]?([^'"\r\n]+)['"]?/m);
  return match?.[1]?.trim() || path.basename(path.dirname(skillPath));
}

function readPyprojectVersion(root) {
  const filePath = path.join(root, 'pyproject.toml');
  if (!existsSync(filePath)) return null;
  const match = readFileSync(filePath, 'utf8').match(/^version\s*=\s*"([^"]+)"/m);
  return match?.[1] ?? null;
}

function readPackageVersion(root) {
  return readJsonIfExists(path.join(root, 'package.json'))?.version ?? null;
}

function detectClient(client, sourceInfo) {
  const cli = CLIENT_CLIS[client];
  const cliPresent = runCaptured(`${cli} --version`, { timeout: 15000 }).ok;
  if (sourceInfo.kind === 'plugin') {
    return detectPluginClient(client, sourceInfo, cliPresent);
  }
  return detectSkillClient(client, sourceInfo, cliPresent);
}

function detectSkillClient(client, sourceInfo, cliPresent) {
  const direct = path.join(homedir(), ...CLIENT_ROOTS[client], sourceInfo.name);
  const aggregate = client === 'codex'
    ? path.join(homedir(), ...CLIENT_ROOTS[client], 'custom', sourceInfo.name)
    : null;
  const exposure = [direct, aggregate].filter(Boolean).find((candidate) => existsSync(path.join(candidate, 'SKILL.md')));
  if (!exposure) {
    return {
      key: client,
      label: CLIENT_LABELS[client],
      cliPresent,
      installed: false,
      mode: 'skill',
      version: null,
      updateable: false,
      detail: 'not installed',
    };
  }

  const resolved = safeRealpath(exposure);
  const targetVersion = readPyprojectVersion(resolved);
  const managed = samePath(resolved, REPO_ROOT) || samePath(safeRealpath(path.join(exposure, '..')), REPO_ROOT);
  const versionKnown = targetVersion || managed;
  const updateable = Boolean(
    sourceInfo.version &&
    targetVersion &&
    targetVersion !== sourceInfo.version,
  );

  return {
    key: client,
    label: CLIENT_LABELS[client],
    cliPresent,
    installed: true,
    mode: 'skill',
    version: targetVersion ?? (managed ? sourceInfo.version : null),
    updateable,
    detail: versionKnown ? 'present' : 'present (manual or unknown version)',
    path: exposure,
    resolved,
  };
}

function detectPluginClient(client, sourceInfo, cliPresent) {
  if (!cliPresent) {
    return {
      key: client,
      label: CLIENT_LABELS[client],
      cliPresent: false,
      installed: false,
      mode: 'plugin',
      version: null,
      updateable: false,
      detail: 'client CLI missing',
    };
  }

  if (client === 'codex') {
    const jsonResult = runCaptured(pluginListCommand(client, sourceInfo, { json: true }), { timeout: 30000 });
    const plugin = jsonResult.ok ? parseCodexPluginList(jsonResult.out, sourceInfo) : null;
    if (plugin?.installed) {
      const version = plugin.version ?? null;
      return pluginStatus(client, sourceInfo, version);
    }
  }

  const listResult = runCaptured(pluginListCommand(client, sourceInfo), { timeout: 30000 });
  const version = listResult.ok && pluginAppearsInList(listResult.out, sourceInfo)
    ? parseVersionNearName(listResult.out, sourceInfo.name)
    : null;
  if (!version && !(listResult.ok && pluginAppearsInList(listResult.out, sourceInfo))) {
    return {
      key: client,
      label: CLIENT_LABELS[client],
      cliPresent: true,
      installed: false,
      mode: 'plugin',
      version: null,
      updateable: false,
      detail: 'not installed',
    };
  }
  return pluginStatus(client, sourceInfo, version);
}

function pluginStatus(client, sourceInfo, version) {
  return {
    key: client,
    label: CLIENT_LABELS[client],
    cliPresent: true,
    installed: true,
    mode: 'plugin',
    version: version ?? 'installed',
    updateable: Boolean(version && sourceInfo.version && version !== sourceInfo.version),
    detail: 'present',
  };
}

function pluginAppearsInList(out, sourceInfo) {
  const escapedName = escapeRegExp(sourceInfo.name);
  const escapedMarketplace = escapeRegExp(sourceInfo.marketplace);
  return new RegExp(`\\b${escapedName}\\b`, 'i').test(out) ||
    new RegExp(`${escapedName}@${escapedMarketplace}`, 'i').test(out);
}

function parseVersionNearName(out, name) {
  const lines = out.split(/\r?\n/);
  const nameRegex = new RegExp(`\\b${escapeRegExp(name)}\\b`, 'i');
  for (let index = 0; index < lines.length; index += 1) {
    if (!nameRegex.test(lines[index])) continue;
    for (const line of lines.slice(index, index + 4)) {
      const match = line.match(/(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)/);
      if (match) return match[1];
    }
  }
  return null;
}

function parseCodexPluginList(out, sourceInfo) {
  try {
    const data = JSON.parse(out);
    const plugins = [...(data.installed ?? []), ...(data.available ?? [])];
    return plugins.find((plugin) => (
      plugin.pluginId === `${sourceInfo.name}@${sourceInfo.marketplace}` ||
      (plugin.name === sourceInfo.name && plugin.marketplaceName === sourceInfo.marketplace)
    )) ?? null;
  } catch {
    return null;
  }
}

async function chooseClients(states) {
  if (argv.clients.length > 0) return argv.clients;
  const selectable = states.filter((state) => state.mode === 'skill' || state.cliPresent);
  if (argv.yes || argv.dryRun) return selectable.map((state) => state.key);

  const picked = await ui.multiselect({
    message: 'Select clients to install/update',
    options: selectable.map((state) => ({
      value: state.key,
      label: state.label,
      hint: statusText(state, false),
    })),
    required: true,
  });
  if (ui.isCancel(picked)) {
    ui.cancel('Cancelled.');
    process.exit(0);
  }
  return picked;
}

async function applyClient(client, sourceInfo, state) {
  if (sourceInfo.kind === 'plugin') {
    return applyPluginClient(client, sourceInfo, state);
  }
  return applySkillClient(client, sourceInfo);
}

async function applySkillClient(client, sourceInfo) {
  const command = `uv run skillpp bootstrap --source ${q(REPO_ROOT)} --client ${client}`;
  runInherit(command);
  if (argv.dryRun) {
    ui.log.message('Dry-run: verification skipped.');
    return { label: CLIENT_LABELS[client], ok: true };
  }

  const refreshed = detectSkillClient(client, sourceInfo, cliPresent(CLIENT_CLIS[client]));
  if (refreshed.installed) {
    ui.log.success(`${CLIENT_LABELS[client]}: installed and verified in discovery root.`);
    return { label: CLIENT_LABELS[client], ok: true };
  }
  ui.log.error(`${CLIENT_LABELS[client]}: not visible after bootstrap.`);
  return { label: CLIENT_LABELS[client], ok: false };
}

async function applyPluginClient(client, sourceInfo, state) {
  runInherit(pluginMarketplaceCommand(client, sourceInfo));
  const actionCommand = state?.installed
    ? pluginUpdateCommand(client, sourceInfo)
    : pluginInstallCommand(client, sourceInfo);
  runInherit(actionCommand);

  if (argv.dryRun) {
    ui.log.message('Dry-run: verification skipped.');
    return { label: CLIENT_LABELS[client], ok: true };
  }

  const refreshed = detectPluginClient(client, sourceInfo, true);
  if (refreshed.installed) {
    ui.log.success(`${CLIENT_LABELS[client]}: ${state?.installed ? 'update' : 'install'} verified in plugin list.`);
    return { label: CLIENT_LABELS[client], ok: true };
  }
  ui.log.error(`${CLIENT_LABELS[client]}: plugin not visible after install/update.`);
  return { label: CLIENT_LABELS[client], ok: false };
}

function pluginMarketplaceCommand(client, sourceInfo) {
  return `${CLIENT_CLIS[client]} plugin marketplace add ${q(REPO_ROOT)}`;
}

function pluginInstallCommand(client, sourceInfo) {
  if (client === 'codex') return `codex plugin add ${sourceInfo.name}@${sourceInfo.marketplace}`;
  return `${CLIENT_CLIS[client]} plugin install ${sourceInfo.name}@${sourceInfo.marketplace}`;
}

function pluginUpdateCommand(client, sourceInfo) {
  if (client === 'codex') return `codex plugin add ${sourceInfo.name}@${sourceInfo.marketplace}`;
  if (client === 'copilot') return `copilot plugin update ${sourceInfo.name}`;
  return `claude plugin update ${sourceInfo.name}@${sourceInfo.marketplace}`;
}

function pluginListCommand(client, sourceInfo, options = {}) {
  if (client === 'codex') {
    return `codex plugin list --marketplace ${sourceInfo.marketplace}${options.json ? ' --json --available' : ''}`;
  }
  return `${CLIENT_CLIS[client]} plugin list`;
}

function runCaptured(command, { timeout = 120000 } = {}) {
  const result = spawnSync(command, {
    shell: true,
    encoding: 'utf8',
    timeout,
  });
  return {
    ok: result.status === 0,
    code: result.status,
    out: `${result.stdout ?? ''}${result.stderr ?? ''}`,
  };
}

function runInherit(command) {
  ui.log.message(pc.dim(`$ ${command}`));
  if (argv.dryRun) return { ok: true, code: 0 };
  const result = spawnSync(command, {
    shell: true,
    stdio: 'inherit',
  });
  return { ok: result.status === 0, code: result.status };
}

function cliPresent(cli) {
  return runCaptured(`${cli} --version`, { timeout: 15000 }).ok;
}

function renderStates(states) {
  const width = Math.max(...states.map((state) => state.label.length));
  return states
    .map((state) => `${pc.bold(state.label.padEnd(width))}  ${statusText(state, true)}`)
    .join('\n');
}

function statusText(state, colored) {
  const color = colored ? pc : plainColors();
  if (!state.cliPresent) {
    const suffix = state.mode === 'skill' ? '; filesystem install still available' : '';
    return color.gray(`CLI missing${suffix}`);
  }
  if (!state.installed) return color.yellow('not installed');
  if (state.updateable) return color.cyan(`update ${state.version} -> ${source.version}`);
  if (state.version && state.version !== 'installed') return color.green(`present (${state.version})`);
  return color.green(state.detail);
}

function safeRealpath(target) {
  try {
    return realpathSync.native(target);
  } catch {
    return path.resolve(target);
  }
}

function samePath(left, right) {
  return path.normalize(left).toLowerCase() === path.normalize(right).toLowerCase();
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function plainColors() {
  return new Proxy({}, { get: () => (value) => String(value) });
}

async function loadUi() {
  try {
    const prompts = await import('@clack/prompts');
    const colors = (await import('picocolors')).default;
    return { ...prompts, pc: colors };
  } catch {
    const color = plainColors();
    return {
      pc: color,
      intro: (message) => console.log(message),
      outro: (message) => console.log(message),
      note: (message, title) => console.log(`${title}\n${message}`),
      cancel: (message) => console.log(message),
      isCancel: () => false,
      confirm: async () => true,
      multiselect: async ({ options }) => options.map((option) => option.value),
      spinner: () => ({
        start: (message) => console.log(message),
        stop: (message) => console.log(message),
      }),
      log: {
        message: (message) => console.log(message),
        step: (message) => console.log(message),
        success: (message) => console.log(message),
        error: (message) => console.error(message),
      },
    };
  }
}

function printHelp() {
  console.log(`skillpp installer

USAGE
  node install.mjs                 interactive install/update
  node install.mjs --status        show client status only
  node install.mjs --dry-run       show commands without modifying anything
  node install.mjs --yes           skip confirmation and select all eligible clients
  node install.mjs --client codex  limit to one client; repeat for more
  node install.mjs --help

FLAGS
  -s, --status   show status and exit
  -n, --dry-run  print commands without running install/update
  -y, --yes      non-interactive confirmation
  -h, --help     show this help

CLIENTS
  Claude Code, Codex, GitHub Copilot CLI

BEHAVIOR
  Plugin manifests present: use client plugin marketplace/install/update commands.
  No plugin manifests: bootstrap this repository through the Python skillpp CLI.

SOURCE
  ${REPO_ROOT}`);
}

main().catch((error) => {
  ui.cancel(String(error?.stack || error));
  process.exit(1);
});
