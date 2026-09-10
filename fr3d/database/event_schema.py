"""Event history schema and immutable seed definition, shared by install/upgrade."""

TABLES = ('event_type', 'event_log', 'event_log_data')
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS event_type (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        provider VARCHAR(64) NOT NULL,
        event_id INT UNSIGNED NOT NULL,
        name VARCHAR(64) NOT NULL,
        category VARCHAR(64) NULL,
        title VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        default_level VARCHAR(16) NOT NULL DEFAULT 'info',
        version SMALLINT UNSIGNED NOT NULL DEFAULT 1,
        UNIQUE KEY uq_event_type (provider, event_id, version),
        UNIQUE KEY uq_event_name (provider, name, version)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin""",
    """CREATE TABLE IF NOT EXISTS event_log (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        occurred_at DATETIME(6) NOT NULL,
        event_type_id BIGINT UNSIGNED NOT NULL,
        level VARCHAR(16) NOT NULL,
        message VARCHAR(1024) NULL,
        FOREIGN KEY (event_type_id) REFERENCES event_type(id),
        INDEX idx_event_log_time (occurred_at),
        INDEX idx_event_log_type (event_type_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin""",
    """CREATE TABLE IF NOT EXISTS event_log_data (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        event_log_id BIGINT UNSIGNED NOT NULL,
        name VARCHAR(64) NOT NULL,
        value JSON NULL,
        FOREIGN KEY (event_log_id) REFERENCES event_log(id) ON DELETE RESTRICT,
        UNIQUE KEY uq_event_log_data_name (event_log_id, name),
        INDEX idx_event_log_data_event (event_log_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin""",
)

# Anonymous MariaDB block: no permanent routines or runtime DDL permissions.
SEED_SQL = """BEGIN NOT ATOMIC
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;
    INSERT INTO event_type (provider, event_id, name, category, title, description, default_level, version)
    SELECT 'fr3d', 3001, 'seed_generated', 'configuration', 'New seed generated',
           'A new seed was generated for the golden configuration.', 'info', 1
    WHERE NOT EXISTS (
        SELECT 1 FROM event_type WHERE provider = 'fr3d' AND version = 1
        AND (event_id = 3001 OR name = 'seed_generated')
    );
    IF (SELECT COUNT(*) FROM event_type WHERE provider = 'fr3d' AND version = 1
        AND (event_id = 3001 OR name = 'seed_generated')) <> 1
       OR NOT EXISTS (
        SELECT 1 FROM event_type WHERE BINARY provider = BINARY 'fr3d'
        AND event_id = 3001 AND BINARY name = BINARY 'seed_generated' AND version = 1
        AND BINARY category = BINARY 'configuration'
        AND BINARY title = BINARY 'New seed generated'
        AND BINARY description = BINARY 'A new seed was generated for the golden configuration.'
        AND BINARY default_level = BINARY 'info'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Conflicting event definition: fr3d/seed_generated/v1';
    END IF;
    COMMIT;
END"""
