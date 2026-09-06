"""Compatibility adapter for the standalone report API; runtime uses the object."""

from fr3d.app.LearningRateReport import DEFAULT_TEMPLATE, Episode, Experiment, LearningRateReport

connect_snake_lab = LearningRateReport.connect_snake_lab
format_number = LearningRateReport.format_number
format_duration = LearningRateReport.format_duration
validate_experiments = LearningRateReport.validate_experiments


def generate_markdown(run_ids=(), *, template_path=DEFAULT_TEMPLATE, connection_factory=connect_snake_lab):
    return LearningRateReport(template_path=template_path, connection_factory=connection_factory).generate_markdown(run_ids)


def load_experiments(run_ids=(), *, connection_factory=connect_snake_lab, limit=None):
    return LearningRateReport(connection_factory=connection_factory).load_experiments(run_ids, limit=limit)


def render_markdown(experiments, *, template_path=DEFAULT_TEMPLATE):
    return LearningRateReport(template_path=template_path).render_markdown(experiments)


def find_completed_experiment(config, project_version, *, connection_factory=connect_snake_lab):
    return LearningRateReport(connection_factory=connection_factory).find_completed_experiment(config, project_version)
