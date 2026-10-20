-- Add weekly recurrence days to existing work shifts.
-- Existing shift behavior applied on every date in its effective range,
-- so legacy records are preserved with all seven weekdays selected.
ALTER TABLE CA_LAM_VIEC
    ADD COLUMN weekday_mask TINYINT UNSIGNED NULL AFTER end_time;

UPDATE CA_LAM_VIEC
SET weekday_mask = 127
WHERE weekday_mask IS NULL;

ALTER TABLE CA_LAM_VIEC
    MODIFY COLUMN weekday_mask TINYINT UNSIGNED NOT NULL;
