#!/usr/bin/env node
import { mkdir, readFile, writeFile, stat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

const appSupportDir = join(homedir(), 'Library', 'Application Support');
const configFile = process.env.ORBITYLABS_CONFIG_FILE || join(appSupportDir, 'OrbityLabs', 'config.json');
const configDir = join(configFile, '..');
const envFile = process.env.HERMES_JARVIS_CONFIG_FILE || join(appSupportDir, 'OrbityLabs', '.env');
const legacyEnvFile = join(appSupportDir, 'Hermes Jarvis', '.env');
const bridgeHealthUrl = process.env.ORBITYLABS_BRIDGE_URL || 'http://127.0.0.1:8787';
const REQUIRED_NODE_MAJOR = 22;
const REQUIRED_NODE_MINOR = 18;

async function readConfig() {
  try { return JSON.parse(await readFile(configFile, 'utf8')); } catch { return { autonomy: 'manual', models: [], default_model: '', agents: {} }; }
}
async function writeConfig(config) {
  await mkdir(configDir, { recursive: true });
  await writeFile(configFile, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
}
function usage() {
  console.log('OrbityLabs runtime configuration\n\nCommands:\n  orbitylabs model [provider:model]\n  orbitylabs agent model <agent-id> <provider:model>\n  orbitylabs config set autonomy auto-safe|manual\n  orbitylabs config get autonomy\n  orbitylabs config list\n  orbitylabs models add provider:model\n  orbitylabs models list\n  orbitylabs doctor');
}

async function fileExists(path) {
  try { await stat(path); return true; } catch { return false; }
}

async function readEnvKeys(path) {
  try {
    const text = await readFile(path, 'utf8');
    const keys = new Set();
    for (const line of text.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
      keys.add(trimmed.split('=', 1)[0].trim());
    }
    return keys;
  } catch {
    return null;
  }
}

async function checkBridge() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    const response = await fetch(`${bridgeHealthUrl}/api/health`, { signal: controller.signal });
    clearTimeout(timeout);
    return response.ok;
  } catch {
    return false;
  }
}

async function doctor() {
  const config = await readConfig();
  const lines = ['OrbityLabs doctor', ''];
  const check = (ok, label) => lines.push(`  ${ok ? '✓' : '✗'} ${label}`);

  lines.push('Runtime configuration');
  check(true, `Config file: ${configFile}`);
  const [nodeMajor, nodeMinor] = process.versions.node.split('.').map(Number);
  const nodeOk = nodeMajor > REQUIRED_NODE_MAJOR || (nodeMajor === REQUIRED_NODE_MAJOR && nodeMinor >= REQUIRED_NODE_MINOR);
  check(nodeOk, `Node.js ${process.versions.node} (>= ${REQUIRED_NODE_MAJOR}.${REQUIRED_NODE_MINOR}.0 required)`);
  check(true, `Autonomy policy: ${config.autonomy || 'manual'}`);
  check(Boolean(config.default_model), config.default_model ? `Default model: ${config.default_model}` : 'Default model: Not configured');
  const agentCount = Object.keys(config.agents || {}).length;
  check(agentCount > 0, agentCount > 0 ? `Agent model routes: ${agentCount} configured` : 'Agent model routes: None configured');

  lines.push('', 'Hermes connection');
  let envKeys = await readEnvKeys(envFile);
  let envPath = envFile;
  if (envKeys === null && !process.env.HERMES_JARVIS_CONFIG_FILE) {
    const legacyKeys = await readEnvKeys(legacyEnvFile);
    if (legacyKeys !== null) { envKeys = legacyKeys; envPath = legacyEnvFile; }
  }
  if (envKeys === null) {
    check(false, `Gateway config: not found at ${envFile}`);
    lines.push('    Run `orbitylabs-connect <http://host:port>` to verify and save a connection.');
  } else {
    check(envKeys.has('HERMES_API_URL'), envKeys.has('HERMES_API_URL') ? `Gateway URL configured (${envPath})` : `Gateway URL missing from ${envPath}`);
    check(envKeys.has('HERMES_API_KEY'), envKeys.has('HERMES_API_KEY') ? 'API key present (value not shown)' : 'API key not set (only safe for gateways without authentication)');
  }

  const bridgeUp = await checkBridge();
  check(bridgeUp, bridgeUp ? `Local bridge reachable at ${bridgeHealthUrl}` : `Local bridge not reachable at ${bridgeHealthUrl} (start it with npm run server or the desktop app)`);

  lines.push('', 'Run `orbitylabs config list` to see all configured values.');
  console.log(lines.join('\n'));
}

const [group, action, value] = process.argv.slice(2);
if (group === 'doctor') { await doctor(); process.exit(0); }

const config = await readConfig();
if (group === 'config' && action === 'set' && value === 'autonomy' && (process.argv[5] === 'auto-safe' || process.argv[5] === 'manual')) {
  config.autonomy = process.argv[5]; await writeConfig(config); console.log(`Autonomy policy saved: ${config.autonomy}`); process.exit(0);
}
if (group === 'config' && action === 'list') { console.log(JSON.stringify(config, null, 2)); process.exit(0); }
if (group === 'config' && action === 'get' && value === 'autonomy') { console.log(config.autonomy || 'manual'); process.exit(0); }
if (group === 'model') {
  if (!action) { console.log(config.default_model || 'Gateway default'); process.exit(0); }
  config.default_model = action; await writeConfig(config); console.log(`Default model route saved: ${action}`); process.exit(0);
}
if (group === 'agent' && action === 'model' && value && process.argv[5]) {
  config.agents ||= {}; config.agents[value] = process.argv[5]; await writeConfig(config); console.log(`Agent ${value} model route saved: ${process.argv[5]}`); process.exit(0);
}
if (group === 'models' && action === 'add' && value) {
  if (!config.models.includes(value)) config.models.push(value);
  await writeConfig(config); console.log(`Model route saved: ${value}`); process.exit(0);
}
if (group === 'models' && action === 'list') { console.log(config.models.length ? config.models.join('\n') : 'No model routes configured.'); process.exit(0); }
usage(); process.exit(1);
