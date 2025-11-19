const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pointCloudApi', {
  choosePointCloud: () => ipcRenderer.invoke('point-cloud:choose'),
});
