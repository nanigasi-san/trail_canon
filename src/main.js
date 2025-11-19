const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

const CHANNELS = {
  POINT_CLOUD_CHOOSE: 'point-cloud:choose',
};

const isDev = process.env.NODE_ENV === 'development';

const createWindow = () => {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  window.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  if (isDev) {
    window.webContents.openDevTools({ mode: 'detach' });
  }
};

const handleChoosePointCloud = async () => {
  const result = await dialog.showOpenDialog({
    title: '点群ファイルを選択',
    filters: [
      { name: 'Point Cloud', extensions: ['xyz', 'txt', 'csv'] },
      { name: 'All Files', extensions: ['*'] },
    ],
    properties: ['openFile'],
  });

  if (result.canceled || !result.filePaths.length) {
    return { canceled: true };
  }

  const filePath = result.filePaths[0];
  const fileName = path.basename(filePath);
  const raw = fs.readFileSync(filePath, 'utf8');

  return { canceled: false, fileName, raw };
};

const registerAppEvents = () => {
  app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      app.quit();
    }
  });
};

const registerIpcHandlers = () => {
  ipcMain.handle(CHANNELS.POINT_CLOUD_CHOOSE, handleChoosePointCloud);
};

registerAppEvents();
registerIpcHandlers();
