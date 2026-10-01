-- Migration: 20261002_email_deduplication.sql
-- Description: Add dedup_hash to EMAIL_OUTBOX and create EMAIL_DEDUP_LOCKS for atomic deduplication

ALTER TABLE EMAIL_OUTBOX
    ADD COLUMN IF NOT EXISTS dedup_hash VARCHAR(64) NULL AFTER deduplication_key;

CREATE INDEX IF NOT EXISTS idx_email_dedup
    ON EMAIL_OUTBOX (recipient_email, dedup_hash, created_at);

CREATE TABLE IF NOT EXISTS EMAIL_DEDUP_LOCKS (
    recipient_email VARCHAR(254) NOT NULL,
    dedup_hash VARCHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_outbox_id BIGINT NULL,
    PRIMARY KEY (recipient_email, dedup_hash),
    KEY idx_email_dedup_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
