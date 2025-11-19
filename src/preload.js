const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pointCloudApi', {
  chooseFile: () => ipcRenderer.invoke('choose-point-cloud'),
});
