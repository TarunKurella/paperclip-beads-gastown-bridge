CREATE TABLE IF NOT EXISTS task_control (
  scope_key TEXT NOT NULL,
  paperclip_id TEXT NOT NULL,
  execution_owner TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(scope_key, paperclip_id)
);

CREATE TABLE IF NOT EXISTS run_locks (
  lock_key TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_control_owner ON task_control(scope_key, execution_owner);
