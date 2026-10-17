-- Additive US37 mapping, Mentor audit, hiring decision, and candidate staging tables.
-- Apply only to an isolated IMS test database until a production rollout is approved.

CREATE TABLE IF NOT EXISTS HRM_MENTOR_LINKS (
    provider_id VARCHAR(32) NOT NULL,
    external_employee_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    external_employee_id VARCHAR(128) NOT NULL,
    ma_nguoi_dung INT NOT NULL,
    approved_by INT NOT NULL,
    approved_at DATETIME NOT NULL,
    PRIMARY KEY (provider_id, external_employee_key),
    UNIQUE KEY uq_hrm_mentor_user (provider_id, ma_nguoi_dung),
    CONSTRAINT fk_hrm_mentor_link_user FOREIGN KEY (ma_nguoi_dung)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_mentor_link_approver FOREIGN KEY (approved_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_MENTOR_SYNC_AUDIT (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    external_employee_id VARCHAR(128) NOT NULL,
    mentor_user_id INT NOT NULL,
    actor_user_id INT NOT NULL,
    changed_fields_json TEXT NOT NULL,
    before_values_json TEXT NOT NULL,
    after_values_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    KEY idx_hrm_mentor_audit_created (created_at),
    CONSTRAINT fk_hrm_mentor_audit_user FOREIGN KEY (mentor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_mentor_audit_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_HIRING_DECISIONS (
    ma_ho_so INT PRIMARY KEY,
    decision_status VARCHAR(16) NOT NULL,
    actor_user_id INT NOT NULL,
    decision_at DATETIME NOT NULL,
    reason VARCHAR(500) NULL,
    CONSTRAINT chk_hrm_hiring_decision_status CHECK (decision_status IN ('APPROVED', 'REVOKED')),
    CONSTRAINT fk_hrm_hiring_decision_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_hiring_decision_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_HIRING_DECISION_HISTORY (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    decision_status VARCHAR(16) NOT NULL,
    actor_user_id INT NOT NULL,
    reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL,
    KEY idx_hrm_hiring_history_profile (ma_ho_so, created_at),
    CONSTRAINT chk_hrm_hiring_history_status CHECK (decision_status IN ('APPROVED', 'REVOKED')),
    CONSTRAINT fk_hrm_hiring_history_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_hiring_history_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_PREVIEWS (
    preview_id CHAR(36) PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    actor_user_id INT NOT NULL,
    ma_ho_so INT NOT NULL,
    snapshot_hash CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    KEY idx_hrm_outbound_preview_profile (provider_id, ma_ho_so, status),
    CONSTRAINT chk_hrm_outbound_preview_status CHECK (status IN ('PENDING', 'APPROVED', 'SENT', 'STALE', 'EXPIRED')),
    CONSTRAINT fk_hrm_outbound_preview_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_outbound_preview_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_PROPOSALS (
    provider_id VARCHAR(32) NOT NULL,
    ma_ho_so INT NOT NULL,
    external_reference VARCHAR(128) NOT NULL,
    candidate_request_id VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL,
    external_employee_id VARCHAR(128) NULL,
    last_payload_hash CHAR(64) NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (provider_id, ma_ho_so),
    UNIQUE KEY uq_hrm_proposal_ref (provider_id, external_reference),
    UNIQUE KEY uq_hrm_proposal_request (provider_id, candidate_request_id),
    CONSTRAINT fk_hrm_proposal_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS HRM_OUTBOUND_HISTORY (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider_id VARCHAR(32) NOT NULL,
    actor_user_id INT NOT NULL,
    ma_ho_so INT NOT NULL,
    external_reference VARCHAR(128) NOT NULL,
    candidate_request_id VARCHAR(128) NULL,
    event_status VARCHAR(32) NOT NULL,
    reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL,
    KEY idx_hrm_outbound_history_created (created_at),
    KEY idx_hrm_outbound_history_profile (ma_ho_so, created_at),
    CONSTRAINT fk_hrm_outbound_history_actor FOREIGN KEY (actor_user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    CONSTRAINT fk_hrm_outbound_history_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
