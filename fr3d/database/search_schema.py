"""Fr3d-owned search accounting tables, shared by install and upgrade."""

TABLES = ('search_state', 'search_parameter_state', 'search_steps')

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS search_state (
        id TINYINT UNSIGNED NOT NULL PRIMARY KEY CHECK (id = 1),
        version INT UNSIGNED NOT NULL,
        revision BIGINT UNSIGNED NOT NULL,
        seed BIGINT UNSIGNED NULL,
        gold_run_id VARCHAR(255) NULL,
        baseline_run_id VARCHAR(255) NULL,
        gold JSON NULL,
        baseline JSON NULL,
        dead_ends JSON NOT NULL,
        parameter_order JSON NOT NULL,
        next_index INT UNSIGNED NOT NULL,
        cycle_end BOOLEAN NOT NULL,
        stagnant_cycles INT UNSIGNED NOT NULL,
        cycle_improved BOOLEAN NOT NULL,
        pending_run_id VARCHAR(255) NULL,
        pending_tweak JSON NULL,
        pending_cycle_end BOOLEAN NOT NULL,
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS search_parameter_state (
        parameter VARCHAR(255) NOT NULL PRIMARY KEY,
        score_window JSON NOT NULL,
        converged BOOLEAN NOT NULL
    ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS search_steps (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        status ENUM('running', 'completed') NOT NULL,
        kind ENUM('parameter', 'baseline', 'seed_rotation', 'cancelled_recovery') NOT NULL,
        parameter VARCHAR(255) NULL,
        seed BIGINT UNSIGNED NOT NULL,
        initial BOOLEAN NOT NULL,
        automatic_arguments JSON NULL,
        remaining_count BIGINT UNSIGNED NULL,
        score_before DOUBLE NULL,
        cycle_end BOOLEAN NOT NULL,
        next_index INT UNSIGNED NOT NULL,
        config JSON NULL,
        submitted_after BIGINT UNSIGNED NULL,
        cancelled_run_id VARCHAR(255) NULL,
        run_id VARCHAR(255) NULL,
        outcome VARCHAR(32) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        completed_at DATETIME(6) NULL,
        UNIQUE KEY search_step_run (run_id),
        active_slot TINYINT GENERATED ALWAYS AS
            (CASE WHEN status = 'running' THEN 1 ELSE NULL END) STORED,
        UNIQUE KEY search_one_running_step (active_slot)
    ) ENGINE=InnoDB""",
)
