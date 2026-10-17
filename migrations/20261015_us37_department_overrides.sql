-- Additive US37 employee-specific department overrides and mapping audit.
-- Apply only to the isolated US37 UAT database before any production rollout.

CREATE TABLE IF NOT EXISTS HRM_EMPLOYEE_DEPARTMENT_OVERRIDES (
    provider_id VARCHAR(32) NOT NULL,
    external_employee_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    external_employee_id VARCHAR(128) NOT NULL,
    external_department_code VARCHAR(128) NULL,
    ma_phong_ban INT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    approved_by INT NOT NULL,
    approved_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    revision INT NOT NULL DEFAULT 1,
    PRIMARY KEY (provider_id, external_employee_key),
    KEY idx_hrm_employee_override_department (provider_id, external_department_code),
    CONSTRAINT fk_hrm_employee_override_department FOREIGN KEY (ma_phong_ban)
        REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_employee_override_actor FOREIGN KEY (approved_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_DEPARTMENT_MAPPING_AUDIT (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    mapping_scope VARCHAR(16) NOT NULL,
    external_department_code VARCHAR(128) NULL,
    external_employee_id VARCHAR(128) NULL,
    event_type VARCHAR(32) NOT NULL,
    before_department_id INT NULL,
    after_department_id INT NULL,
    reason VARCHAR(500) NOT NULL,
    actor_user_id INT NOT NULL,
    created_at DATETIME NOT NULL,
    KEY idx_hrm_department_audit_created (provider_id, created_at),
    KEY idx_hrm_department_audit_employee (provider_id, external_employee_id, created_at),
    CONSTRAINT chk_hrm_department_mapping_scope CHECK (mapping_scope IN ('GLOBAL', 'EMPLOYEE')),
    CONSTRAINT fk_hrm_department_mapping_audit_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
