-- Queryable runtime configurations, one row per simulation run.
-- Apply while the SnakeLab service is stopped. Safe to reapply.
CREATE TABLE IF NOT EXISTS configurations (
    run_id CHAR(36) NOT NULL PRIMARY KEY,
    epochs INT UNSIGNED NOT NULL,
    seed BIGINT UNSIGNED NOT NULL,
    game_board_width INT UNSIGNED NOT NULL,
    game_board_height INT UNSIGNED NOT NULL,
    game_initial_snake_length INT UNSIGNED NOT NULL,
    game_max_moves_multiplier INT UNSIGNED NOT NULL,
    game_rewards_food DOUBLE NOT NULL,
    game_rewards_wall DOUBLE NOT NULL,
    game_rewards_snake DOUBLE NOT NULL,
    game_rewards_max_moves DOUBLE NOT NULL,
    game_rewards_empty DOUBLE NOT NULL,
    game_rewards_closer_to_food DOUBLE NOT NULL,
    game_rewards_further_from_food DOUBLE NOT NULL,
    model_hidden_size INT UNSIGNED NOT NULL,
    model_layers INT UNSIGNED NOT NULL,
    model_dropout DOUBLE NOT NULL,
    training_sequence_length INT UNSIGNED NOT NULL,
    training_batch_size INT UNSIGNED NOT NULL,
    training_replay_max_frames INT UNSIGNED NOT NULL,
    training_learning_rate DOUBLE NOT NULL,
    training_gamma DOUBLE NOT NULL,
    training_tau DOUBLE NOT NULL,
    training_max_gradient_norm DOUBLE NOT NULL,
    epsilon_initial DOUBLE NOT NULL,
    epsilon_minimum DOUBLE NOT NULL,
    epsilon_decay DOUBLE NOT NULL,

    CONSTRAINT fk_configuration_run
        FOREIGN KEY (run_id)
        REFERENCES simulation_runs(run_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
