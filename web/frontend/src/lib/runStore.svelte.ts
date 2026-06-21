/**
 * Cross-tab store for the most recent run — Author tab kicks one off via
 * Push/Run, Run tab displays the streaming logs and final env.
 */

export type RunStatus = 'idle' | 'pushing' | 'running' | 'done' | 'error';

class RunStore {
  status = $state<RunStatus>('idle');
  taskId = $state<string | null>(null);
  exitCode = $state<number | null>(null);
  errorMsg = $state<string | null>(null);
  logs = $state<string[]>([]);
  pushOutput = $state<string>('');

  reset() {
    this.status = 'idle';
    this.taskId = null;
    this.exitCode = null;
    this.errorMsg = null;
    this.logs = [];
    this.pushOutput = '';
  }
}

export const runStore = new RunStore();
