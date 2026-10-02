-- Migration: 20261002_email_attachments.sql
-- Description: Add EMAIL_ATTACHMENTS table and enhance EMAIL_OUTBOX for attachments

SET @column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'EMAIL_OUTBOX'
      AND COLUMN_NAME = 'body_html'
);
SET @migration_sql = IF(@column_exists = 0,
    'ALTER TABLE EMAIL_OUTBOX ADD COLUMN body_html LONGTEXT NULL AFTER body',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'EMAIL_OUTBOX'
      AND COLUMN_NAME = 'has_attachments'
);
SET @migration_sql = IF(@column_exists = 0,
    'ALTER TABLE EMAIL_OUTBOX ADD COLUMN has_attachments TINYINT(1) NOT NULL DEFAULT 0 AFTER body_html',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

CREATE TABLE IF NOT EXISTS EMAIL_ATTACHMENTS (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    email_id BIGINT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    disposition ENUM('attachment', 'inline') NOT NULL DEFAULT 'attachment',
    content_id VARCHAR(100) NULL,
    checksum_sha256 CHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_email_attachments_outbox
        FOREIGN KEY (email_id) REFERENCES EMAIL_OUTBOX(id) ON DELETE CASCADE,
    CONSTRAINT chk_attachment_file_size
        CHECK (file_size > 0 AND file_size <= 10485760),
    CONSTRAINT chk_attachment_disposition
        CHECK (disposition IN ('attachment', 'inline')),
    KEY idx_email_attachments_lookup (email_id, disposition),
    UNIQUE KEY uq_attachment_cid (email_id, content_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
