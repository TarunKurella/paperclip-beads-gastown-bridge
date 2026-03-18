CREATE TABLE IF NOT EXISTS id_map_scoped (
  scope_key TEXT NOT NULL,
  paperclip_id TEXT NOT NULL,
  beads_id TEXT NOT NULL,
  gastown_target TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(scope_key, paperclip_id)
);

CREATE INDEX IF NOT EXISTS idx_id_map_scoped_beads ON id_map_scoped(scope_key, beads_id);
