import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const python = process.env.HERMES_JARVIS_PYTHON || resolve(root, '.venv', 'bin', 'python');
const output = resolve(root, 'desktop-build', 'hermes-jarvis-server');

function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit', env: process.env });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (!existsSync(python)) {
  console.error('Hermes Jarvis needs .venv before it can package the desktop bridge. Run the local setup from README.md once.');
  process.exit(1);
}

run('npm', ['run', 'build']);
const probe = spawnSync(python, ['-m', 'PyInstaller', '--version'], { cwd: root, stdio: 'ignore' });
if (probe.status !== 0) run(python, ['-m', 'pip', 'install', 'pyinstaller>=6.10,<7']);
run(python, [
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', 'hermes-jarvis-server',
  '--paths', resolve(root, 'backend'), '--distpath', resolve(root, 'desktop-build'),
  '--workpath', resolve(root, '.desktop-pyinstaller'), '--specpath', resolve(root, '.desktop-pyinstaller'),
  resolve(root, 'backend', 'hermes_jarvis', 'desktop_server.py'),
]);
if (!existsSync(output)) {
  console.error('The desktop bridge binary was not produced.');
  process.exit(1);
}
run('npx', ['electron-builder', '--mac', '--publish', 'never']);
