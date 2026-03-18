CREATE TABLE IF NOT EXISTS id_map (
  paperclip_id TEXT PRIMARY KEY,
  beads_id TEXT NOT NULL,
  gastown_target TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_id_map_beads_id ON id_map(beads_id);
