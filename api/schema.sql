-- New database schema; not a migration for the earlier Sites app.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS submission_receipts (
  idempotency_key TEXT PRIMARY KEY NOT NULL,
  profile_id TEXT NOT NULL UNIQUE,
  payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
  delete_hash TEXT NOT NULL CHECK(length(delete_hash) = 64),
  created_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY NOT NULL REFERENCES submission_receipts(profile_id),
  created_at TEXT NOT NULL,
  author TEXT NOT NULL,
  model TEXT NOT NULL,
  payload TEXT NOT NULL,
  payload_bytes INTEGER NOT NULL CHECK(payload_bytes BETWEEN 1 AND 131072),
  CHECK(length(CAST(payload AS BLOB)) = payload_bytes)
);

CREATE INDEX IF NOT EXISTS idx_profiles_created_id ON profiles(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_model_created_id ON profiles(model, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS submission_limits (
  key TEXT PRIMARY KEY NOT NULL,
  count INTEGER NOT NULL CHECK(count BETWEEN 1 AND 20),
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_submission_limits_expiry ON submission_limits(expires_at);
