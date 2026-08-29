#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

const configFile = process.env.ORBITYLABS_CONFIG_FILE || join(homedir(), 'Library', 'Application Support', 'OrbityLabs', 'config.json');
const configDir = join(configFile, '..');

async function readConfig() {
  try { return JSON.parse(await readFile(configFile, 'utf8')); } catch { return { autonomy: 'manual', models: [], default_model: '', agents: {} }; }
}
async function writeConfig(config) {
  await mkdir(configDir, { recursive: true });
  await writeFile(configFile, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
}
function usage() {
  console.log('OrbityLabs runtime configuration\n\nCommands:\n  orbitylabs model [provider:model]\n  orbitylabs agent model <agent-id> <provider:model>\n  orbitylabs config set autonomy auto-safe|manual\n  orbitylabs config get autonomy\n  orbitylabs config list\n  orbitylabs models add provider/model\n  orbitylabs models list');
}
const [group, action, value] = process.argv.slice(2);
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
