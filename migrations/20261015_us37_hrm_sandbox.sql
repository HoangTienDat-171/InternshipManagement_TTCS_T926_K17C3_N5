-- US37 HRM integration storage. Apply only to an isolated/test IMS database
-- until the owner approves production field-ownership and mapping policies.

CREATE TABLE IF NOT EXISTS HRM_DEPARTMENT_MAPPINGS (
    provider_id VARCHAR(32) NOT NULL,
    external_department_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    external_department_code VARCHAR(128) NOT NULL,
    ma_phong_ban INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_id, external_department_key),
    CONSTRAINT fk_hrm_department_mapping_department
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_EMPLOYEE_DIRECTORY (
    provider_id VARCHAR(32) NOT NULL,
    external_employee_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    external_employee_id VARCHAR(128) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    work_email VARCHAR(254) NULL,
    phone VARCHAR(40) NULL,
    department_code VARCHAR(128) NULL,
    department VARCHAR(200) NULL,
    ma_phong_ban INT NULL,
    job_title VARCHAR(200) NULL,
    employment_status VARCHAR(16) NOT NULL,
    source_updated_at VARCHAR(64) NULL,
    synced_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_id, external_employee_key),
    KEY idx_hrm_employee_name (full_name),
    CONSTRAINT fk_hrm_employee_department
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_SYNC_PREVIEWS (
    preview_id CHAR(36) PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    actor_user_id INT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    KEY idx_hrm_preview_actor_status (actor_user_id, status),
    CONSTRAINT fk_hrm_preview_actor
        FOREIGN KEY (actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_SYNC_HISTORY (
    id INT AUTO_INCREMENT PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    actor_user_id INT NOT NULL,
    created_at DATETIME NOT NULL,
    total_count INT NOT NULL,
    created_count INT NOT NULL,
    updated_count INT NOT NULL,
    unchanged_count INT NOT NULL,
    skipped_count INT NOT NULL,
    error_count INT NOT NULL,
    status VARCHAR(16) NOT NULL,
    KEY idx_hrm_history_created (created_at),
    CONSTRAINT fk_hrm_history_actor
        FOREIGN KEY (actor_user_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_SYNC_LOCKS (
    provider_id VARCHAR(32) PRIMARY KEY,
    lock_token CHAR(36) NULL,
    lease_until DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO HRM_SYNC_LOCKS (provider_id, lock_token, lease_until)
VALUES ('sandbox', NULL, NULL);
