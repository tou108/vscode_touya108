'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('switchBt', {
  // 接続 / 切断
  connect:    (mac)      => ipcRenderer.invoke('bt:connect', mac),
  disconnect: ()         => ipcRenderer.invoke('bt:disconnect'),

  // ボタン押下・解放
  button: (name, pressed) => ipcRenderer.invoke('bt:button', name, pressed),

  // スティック
  stick: (side, x, y) => ipcRenderer.invoke('bt:stick', side, x, y),

  // 全リセット
  reset: () => ipcRenderer.invoke('bt:reset'),

  // マクロ実行 (ステップ配列を渡す)
  runMacro: (steps) => ipcRenderer.invoke('bt:runMacro', steps),
  stopMacro: ()     => ipcRenderer.invoke('bt:stopMacro'),

  // イベント購読
  onEvent: (cb) => {
    ipcRenderer.on('bt:event', (_e, data) => cb(data));
  },
  offEvents: () => {
    ipcRenderer.removeAllListeners('bt:event');
  },
});
