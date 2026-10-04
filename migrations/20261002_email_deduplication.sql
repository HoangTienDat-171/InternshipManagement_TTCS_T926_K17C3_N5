-- Migration: 20261002_email_deduplication.sql
-- Description: Add dedup_hash to EMAIL_OUTBOX and create EMAIL_DEDUP_LOCKS for atomic deduplication

SET @column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'EMAIL_OUTBOX'
      AND COLUMN_NAME = 'dedup_hash'
);
SET @migration_sql = IF(@column_exists = 0,
    'ALTER TABLE EMAIL_OUTBOX ADD COLUMN dedup_hash VARCHAR(64) NULL AFTER deduplication_key',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @index_exists = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'EMAIL_OUTBOX'
      AND INDEX_NAME = 'idx_email_dedup'
);
SET @migration_sql = IF(@index_exists = 0,
    'CREATE INDEX idx_email_dedup ON EMAIL_OUTBOX (recipient_email, dedup_hash, created_at)',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

CREATE TABLE IF NOT EXISTS EMAIL_DEDUP_LOCKS (
    recipient_email VARCHAR(254) NOT NULL,
    dedup_hash VARCHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_outbox_id BIGINT NULL,
    PRIMARY KEY (recipient_email, dedup_hash),
    KEY idx_email_dedup_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
