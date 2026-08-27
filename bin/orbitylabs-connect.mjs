#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const script = join(packageRoot, 'scripts', 'connect-hermes.py');
const result = spawnSync('python3', [script, ...process.argv.slice(2)], { stdio: 'inherit' });

if (result.error) {
  console.error(`Could not start the OrbityLabs connector: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
