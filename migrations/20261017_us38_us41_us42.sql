-- Sprint 4: QR attendance credentials, backup metadata, and activity audit.
-- Additive migration. It does not rewrite CHAM_CONG rows or existing account data.

CREATE TABLE IF NOT EXISTS IMS_ATTENDANCE_SOURCES (
    attendance_id BIGINT NOT NULL PRIMARY KEY,
    source ENUM('MANUAL','QR','CARD') NOT NULL DEFAULT 'MANUAL',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_ims_attendance_source_record FOREIGN KEY (attendance_id)
        REFERENCES CHAM_CONG(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS IMS_ATTENDANCE_QR_CREDENTIALS (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    ma_nguoi_dung INT NOT NULL,
    issued_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    used_at DATETIME(6) NULL,
    attendance_id BIGINT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_ims_attendance_qr_user_expiry (ma_nguoi_dung, expires_at),
    CONSTRAINT fk_ims_attendance_qr_user FOREIGN KEY (ma_nguoi_dung)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    CONSTRAINT fk_ims_attendance_qr_record FOREIGN KEY (attendance_id)
        REFERENCES CHAM_CONG(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS IMS_AUDIT_LOG (
    event_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_user_id INT NULL,
    actor_name VARCHAR(255) NULL,
    action VARCHAR(120) NOT NULL,
    resource VARCHAR(100) NOT NULL,
    resource_id VARCHAR(120) NULL,
    outcome ENUM('SUCCESS','FAILURE') NOT NULL,
    metadata JSON NULL,
    ip_address VARCHAR(45) NULL,
    session_id VARCHAR(64) NULL,
    request_id VARCHAR(128) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_ims_audit_created (created_at, event_id),
    KEY idx_ims_audit_actor (actor_user_id, created_at),
    KEY idx_ims_audit_action (action, created_at),
    KEY idx_ims_audit_resource (resource, resource_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS IMS_BACKUP_SETTINGS (
    id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    schedule_enabled TINYINT(1) NOT NULL DEFAULT 0,
    interval_hours SMALLINT UNSIGNED NOT NULL DEFAULT 24,
    retention_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    updated_by INT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT chk_ims_backup_settings_singleton CHECK (id = 1),
    CONSTRAINT fk_ims_backup_settings_actor FOREIGN KEY (updated_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO IMS_BACKUP_SETTINGS (id, schedule_enabled, interval_hours, retention_count)
VALUES (1, 0, 24, 0);

CREATE TABLE IF NOT EXISTS IMS_BACKUP_JOBS (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    backup_type ENUM('MANUAL','SCHEDULED','RESTORE_VERIFICATION') NOT NULL,
    status ENUM('RUNNING','SUCCESS','FAILED','EXPIRED') NOT NULL,
    started_by INT NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    file_name VARCHAR(255) NULL,
    file_size_bytes BIGINT UNSIGNED NULL,
    checksum_sha256 CHAR(64) NULL,
    checksum_status ENUM('PENDING','VALID','INVALID') NOT NULL DEFAULT 'PENDING',
    checksum_checked_at DATETIME(6) NULL,
    manifest JSON NULL,
    error_code VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_ims_backup_created (created_at, id),
    KEY idx_ims_backup_status (status, started_at),
    CONSTRAINT fk_ims_backup_job_actor FOREIGN KEY (started_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
