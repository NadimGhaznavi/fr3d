-- Allow repeated configurations while retaining every run and its episodes.
-- Safe to reapply; run_id remains unique and config_hash remains indexed.
ALTER TABLE simulation_runs
    DROP INDEX IF EXISTS uq_simulation_experiment;
