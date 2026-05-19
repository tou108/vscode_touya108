'use strict';
const { app, BrowserWindow, Menu, ipcMain } = require('electron');
const path  = require('path');
const { spawn } = require('child_process');

let btProc   = null;
let mainWin  = null;
let macroTimer = null;

function getBtScriptPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'src', 'switch_bt.py');
  }
  return path.join(__dirname, 'src', 'switch_bt.py');
}

function startBtProc() {
  if (btProc) return;
  const script = getBtScriptPath();
  const python = process.platform === 'win32' ? 'python' : 'python3';
  btProc = spawn(python, [script], { stdio: ['pipe', 'pipe', 'pipe'] });
  btProc.stdout.on('data', (chunk) => {
    const lines = chunk.toString().split('\n');
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const ev = JSON.parse(line);
        if (mainWin && !mainWin.isDestroyed()) mainWin.webContents.send('bt:event', ev);
      } catch {}
    }
  });
  btProc.stderr.on('data', (d) => {
    const msg = d.toString().trim();
    if (msg && mainWin && !mainWin.isDestroyed())
      mainWin.webContents.send('bt:event', { type: 'info', msg });
  });
  btProc.on('close', () => {
    btProc = null;
    if (mainWin && !mainWin.isDestroyed())
      mainWin.webContents.send('bt:event', { type: 'status', status: 'disconnected' });
  });
}

function sendBt(obj) {
  if (!btProc) startBtProc();
  try { btProc.stdin.write(JSON.stringify(obj) + '\n'); } catch (e) {}
}

function setupIpc() {
  ipcMain.handle('bt:connect',    (_e, mac) => { startBtProc(); sendBt({ type: 'connect', mac }); });
  ipcMain.handle('bt:disconnect', ()        => { sendBt({ type: 'disconnect' }); });
  ipcMain.handle('bt:button',     (_e, n, p) => { sendBt({ type: 'button', name: n, pressed: p }); });
  ipcMain.handle('bt:stick',      (_e, s, x, y) => { sendBt({ type: 'stick', side: s, x, y }); });
  ipcMain.handle('bt:reset',      ()        => { sendBt({ type: 'reset' }); });

  ipcMain.handle('bt:runMacro', (_e, steps) => {
    if (macroTimer) { clearTimeout(macroTimer); macroTimer = null; }
    let idx = 0;
    function executeStep() {
      if (idx >= steps.length) {
        sendBt({ type: 'reset' });
        if (mainWin && !mainWin.isDestroyed())
          mainWin.webContents.send('bt:event', { type: 'macroEnd' });
        return;
      }
      const step = steps[idx++];
      sendBt({ type: 'reset' });
      if (step.buttons) for (const btn of step.buttons) sendBt({ type: 'button', name: btn, pressed: true });
      if (step.stick) {
        if (step.stick.L) sendBt({ type: 'stick', side: 'L', x: step.stick.L.x, y: step.stick.L.y });
        if (step.stick.R) sendBt({ type: 'stick', side: 'R', x: step.stick.R.x, y: step.stick.R.y });
      }
      macroTimer = setTimeout(executeStep, step.duration || 100);
    }
    executeStep();
  });

  ipcMain.handle('bt:stopMacro', () => {
    if (macroTimer) { clearTimeout(macroTimer); macroTimer = null; }
    sendBt({ type: 'reset' });
    if (mainWin && !mainWin.isDestroyed())
      mainWin.webContents.send('bt:event', { type: 'macroStopped' });
  });
}

function createWindow() {
  mainWin = new BrowserWindow({
    width: 1280, height: 900, minWidth: 900, minHeight: 600,
    title: 'MHXX 護石スナイプ統合ツール',
    icon: path.join(__dirname, 'assets', 'icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'src', 'preload.js'),
    },
    backgroundColor: '#0e0f11',
    show: false,
  });
  mainWin.loadFile(path.join(__dirname, 'src', 'index.html'));
  mainWin.once('ready-to-show', () => mainWin.show());
  Menu.setApplicationMenu(null);
}

app.whenReady().then(() => {
  setupIpc();
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => {
  if (btProc) try { btProc.kill(); } catch {}
  if (process.platform !== 'darwin') app.quit();
});
