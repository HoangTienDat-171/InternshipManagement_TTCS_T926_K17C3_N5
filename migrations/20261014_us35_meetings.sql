-- US35/US36: meeting scheduling with participant history.
-- Safe to re-run; existing application data is not changed or removed.
CREATE TABLE IF NOT EXISTS LICH_HOP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    location VARCHAR(500) NULL,
    meeting_url VARCHAR(2000) NULL,
    organizer_id INT NOT NULL,
    status ENUM('SCHEDULED','CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
    version INT UNSIGNED NOT NULL DEFAULT 1,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    request_hash CHAR(64) NOT NULL,
    cancelled_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_meeting_time CHECK (end_at > start_at),
    KEY idx_meeting_schedule (status, start_at, id),
    KEY idx_meeting_organizer (organizer_id, created_at),
    CONSTRAINT fk_meeting_organizer FOREIGN KEY (organizer_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS LICH_HOP_NGUOI_THAM_GIA (
    meeting_id BIGINT NOT NULL,
    user_id INT NOT NULL,
    status ENUM('INVITED','REMOVED') NOT NULL DEFAULT 'INVITED',
    invited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at DATETIME NULL,
    PRIMARY KEY (meeting_id, user_id),
    KEY idx_meeting_attendee (user_id, status, meeting_id),
    CONSTRAINT fk_meeting_attendee_meeting FOREIGN KEY (meeting_id)
        REFERENCES LICH_HOP(id) ON DELETE CASCADE,
    CONSTRAINT fk_meeting_attendee_user FOREIGN KEY (user_id)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
