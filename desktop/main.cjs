const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');

let serverProcess;
let mainWindow;
let notifiedVersion = '';
const releaseApi = 'https://api.github.com/repos/judahrumende/HERMES-CONNECTOR/releases/latest';

async function checkForUpdate() {
  try {
    const response = await fetch(releaseApi, { headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'OrbityLabs' } });
    if (!response.ok) return;
    const release = await response.json();
    const version = String(release.tag_name || '').replace(/^v/, '');
    if (!version || version === app.getVersion()) return;
    const asset = (release.assets || []).find(item => item.name === 'OrbityLabs-' + version + '-arm64.dmg');
    if (asset && version !== notifiedVersion && mainWindow && !mainWindow.isDestroyed()) {
      notifiedVersion = version;
      const result = await dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: 'OrbityLabs update available',
        message: 'OrbityLabs ' + version + ' is ready.',
        detail: 'Download the latest desktop build to get the newest fixes.',
        buttons: ['Update', 'Later'],
        defaultId: 0,
        cancelId: 1,
      });
      if (result.response === 0) await shell.openExternal(asset.browser_download_url);
    }
  } catch { /* Updates remain optional when GitHub is unavailable. */ }
}

function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(error => error ? reject(error) : resolve(address.port));
    });
  });
}

async function waitForServer(url) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/health`);
      if (response.ok) return;
    } catch { /* the bridge is still starting */ }
    await new Promise(resolve => setTimeout(resolve, 180));
  }
  throw new Error('The Hermes Jarvis local bridge did not start within 15 seconds.');
}

function startServer(port) {
  const bindHost = process.env.HERMES_JARVIS_BIND_HOST || '0.0.0.0';
  const packagedBinary = path.join(process.resourcesPath, 'server', 'hermes-jarvis-server');
  const configFile = path.join(app.getPath('appData'), 'Hermes Jarvis', '.env');
  const env = {
    ...process.env,
    HERMES_JARVIS_CONFIG_FILE: configFile,
    HERMES_JARVIS_STATE_DIR: app.getPath('userData'),
    HERMES_JARVIS_DIST_DIR: app.isPackaged ? path.join(process.resourcesPath, 'dist') : path.join(__dirname, '..', 'dist'),
  };
  if (app.isPackaged) {
    return spawn(packagedBinary, ['--host', bindHost, '--port', String(port)], { env, stdio: 'ignore' });
  }
  const python = process.env.HERMES_JARVIS_PYTHON || path.join(__dirname, '..', '.venv', 'bin', 'python');
  return spawn(python, ['-m', 'uvicorn', 'hermes_jarvis.app:app', '--app-dir', path.join(__dirname, '..', 'backend'), '--host', bindHost, '--port', String(port)], { env, stdio: 'inherit' });
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1000,
    minHeight: 680,
    backgroundColor: '#ffffff',
    title: 'OrbityLabs',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  mainWindow.loadURL(url);
}

app.whenReady().then(async () => {
  try {
    const port = await reservePort();
    const url = `http://127.0.0.1:${port}`;
    serverProcess = startServer(port);
    serverProcess.once('exit', code => {
      if (code && mainWindow && !mainWindow.isDestroyed()) {
        dialog.showErrorBox('OrbityLabs stopped', 'The local OrbityLabs bridge exited unexpectedly. Reopen the app to try again.');
      }
    });
    await waitForServer(url);
    createWindow(url);
    void checkForUpdate();
    setInterval(checkForUpdate, 15 * 60 * 1000);
  } catch (error) {
    dialog.showErrorBox('OrbityLabs could not start', error instanceof Error ? error.message : String(error));
    app.quit();
  }
});

app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => {
  if (serverProcess && !serverProcess.killed) serverProcess.kill();
});
