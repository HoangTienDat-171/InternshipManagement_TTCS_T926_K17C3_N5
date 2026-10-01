-- Migration: 20261002_email_attachments.sql
-- Description: Add EMAIL_ATTACHMENTS table and enhance EMAIL_OUTBOX for attachments

ALTER TABLE EMAIL_OUTBOX
    ADD COLUMN IF NOT EXISTS body_html LONGTEXT NULL AFTER body,
    ADD COLUMN IF NOT EXISTS has_attachments TINYINT(1) NOT NULL DEFAULT 0 AFTER body_html;

CREATE TABLE IF NOT EXISTS EMAIL_ATTACHMENTS (
    id VARCHAR(36) NOT NULL PRIMARY KEY,            -- UUID v4
    email_id BIGINT NOT NULL,                       -- Foreign Key referencing EMAIL_OUTBOX
    filename VARCHAR(255) NOT NULL,                 -- Original file name
    file_path VARCHAR(500) NOT NULL,                -- Absolute path / Object storage key
    mime_type VARCHAR(127) NOT NULL,                -- Content-Type
    file_size BIGINT UNSIGNED NOT NULL,             -- Bytes (<= 10MB per file)
    disposition ENUM('attachment', 'inline') NOT NULL DEFAULT 'attachment',
    content_id VARCHAR(100) NULL,                   -- CID for inline images (<img src="cid:xyz">)
    checksum_sha256 CHAR(64) NULL,                 -- Integrity verification hash
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints & Indexes
    CONSTRAINT fk_email_attachments_outbox 
        FOREIGN KEY (email_id) REFERENCES EMAIL_OUTBOX(id) ON DELETE CASCADE,
    CONSTRAINT chk_attachment_file_size 
        CHECK (file_size > 0 AND file_size <= 10485760), -- 10MB Max per file
    CONSTRAINT chk_attachment_disposition 
        CHECK (disposition IN ('attachment', 'inline')),
    KEY idx_email_attachments_lookup (email_id, disposition),
    UNIQUE KEY uq_attachment_cid (email_id, content_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
