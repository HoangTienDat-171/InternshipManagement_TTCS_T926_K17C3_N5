-- Additive catalog metadata and local HRM connection registry.
-- Preserve existing PHONG_BAN / TRUONG_DAI_HOC primary keys and all US37 history.

CREATE TABLE IF NOT EXISTS IMS_DEPARTMENT_CATALOG_META (
    ma_phong_ban INT NOT NULL,
    ma_dinh_danh VARCHAR(32) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ma_phong_ban),
    UNIQUE KEY uq_ims_department_code (ma_dinh_danh),
    CONSTRAINT fk_ims_department_meta_department
        FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO IMS_DEPARTMENT_CATALOG_META (ma_phong_ban, ma_dinh_danh, is_active)
SELECT ma_phong_ban, CONCAT('PB-', LPAD(CAST(ma_phong_ban AS CHAR), 4, '0')), 1
FROM PHONG_BAN;

CREATE TABLE IF NOT EXISTS IMS_UNIVERSITY_CATALOG_META (
    ma_truong INT NOT NULL,
    ma_dinh_danh VARCHAR(32) NULL,
    ten_viet_tat VARCHAR(50) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ma_truong),
    UNIQUE KEY uq_ims_university_code (ma_dinh_danh),
    CONSTRAINT fk_ims_university_meta_university
        FOREIGN KEY (ma_truong) REFERENCES TRUONG_DAI_HOC(ma_truong) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO IMS_UNIVERSITY_CATALOG_META (ma_truong, is_active)
SELECT ma_truong, 1 FROM TRUONG_DAI_HOC;

CREATE TABLE IF NOT EXISTS IMS_MASTER_DATA_AUDIT (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    entity_type VARCHAR(24) NOT NULL,
    entity_id INT NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    before_json TEXT NULL,
    after_json TEXT NOT NULL,
    actor_user_id INT NOT NULL,
    created_at DATETIME NOT NULL,
    KEY idx_ims_master_audit_entity (entity_type, entity_id, created_at),
    KEY idx_ims_master_audit_created (created_at),
    CONSTRAINT fk_ims_master_audit_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_CONNECTIONS (
    connection_id VARCHAR(32) NOT NULL,
    connection_name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(32) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    state VARCHAR(16) NOT NULL,
    credential_ref VARCHAR(255) NULL,
    last_checked_at DATETIME NULL,
    last_check_message VARCHAR(255) NULL,
    created_by INT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (connection_id),
    KEY idx_hrm_connections_state (state),
    CONSTRAINT fk_hrm_connection_creator FOREIGN KEY (created_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_ACTIVE_CONNECTION (
    singleton_id TINYINT NOT NULL,
    active_connection_id VARCHAR(32) NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (singleton_id),
    CONSTRAINT chk_hrm_active_connection_singleton CHECK (singleton_id = 1),
    CONSTRAINT fk_hrm_active_connection FOREIGN KEY (active_connection_id)
        REFERENCES HRM_CONNECTIONS(connection_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO HRM_ACTIVE_CONNECTION (singleton_id, active_connection_id, revision, updated_at)
VALUES (1, NULL, 1, CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS HRM_CONNECTION_AUDIT (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    connection_id VARCHAR(32) NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    actor_user_id INT NOT NULL,
    details VARCHAR(500) NULL,
    created_at DATETIME NOT NULL,
    KEY idx_hrm_connection_audit (connection_id, created_at),
    CONSTRAINT fk_hrm_connection_audit_connection FOREIGN KEY (connection_id)
        REFERENCES HRM_CONNECTIONS(connection_id) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_connection_audit_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
