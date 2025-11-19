const DEFAULT_STATE = {
  fileName: '未読込み',
  meshSize: 1,
  points: [],
  stats: null,
  grid: null,
  message: '点群ファイルを読み込んでください。',
};

export class AppState {
  constructor(initialState = {}) {
    this.state = { ...DEFAULT_STATE, ...initialState };
    this.listeners = new Set();
  }

  getSnapshot() {
    return { ...this.state };
  }

  subscribe(listener) {
    this.listeners.add(listener);
    listener(this.getSnapshot());
    return () => this.listeners.delete(listener);
  }

  update(patch) {
    const nextState = typeof patch === 'function' ? patch(this.getSnapshot()) : patch;
    this.state = { ...this.state, ...nextState };
    this.emit();
  }

  emit() {
    const snapshot = this.getSnapshot();
    this.listeners.forEach((listener) => listener(snapshot));
  }
}
