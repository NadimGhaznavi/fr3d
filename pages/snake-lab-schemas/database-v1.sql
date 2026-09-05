CREATE TABLE IF NOT EXISTS simulation_runs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    run_id CHAR(36) NOT NULL UNIQUE,

    project_version VARCHAR(32) NOT NULL,
    config JSON NOT NULL,
    config_hash CHAR(64) NOT NULL,

    status VARCHAR(16) NOT NULL,

    episode_count INT UNSIGNED NULL,
    high_score INT UNSIGNED NULL,

    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,

    error_message TEXT NULL,

    UNIQUE KEY uq_simulation_experiment (project_version, config_hash),
    INDEX idx_config_hash (config_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS simulation_episodes (
    run_id CHAR(36) NOT NULL,
    episode INT UNSIGNED NOT NULL,

    score INT UNSIGNED NOT NULL,
    steps INT UNSIGNED NOT NULL,

    epsilon DOUBLE NULL,
    loss DOUBLE NULL,

    PRIMARY KEY (run_id, episode),

    CONSTRAINT fk_episode_run
        FOREIGN KEY (run_id)
        REFERENCES simulation_runs(run_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
