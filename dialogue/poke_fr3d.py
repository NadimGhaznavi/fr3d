"""Print a database-populated experiment prompt without contacting the LLM."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from constants.DDatabase import DDatabase
from dialogue.learning_rate import DEFAULT_TEMPLATE, generate_markdown


def load_database_environment(path: Path) -> None:
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key = key.strip()
            if not separator or not key.startswith("FR3D_DB_"):
                continue
            parts = shlex.split(value, comments=True)
            if len(parts) > 1:
                raise ValueError(f"Invalid value for {key} in database environment file")
            os.environ.setdefault(key, parts[0] if parts else "")
    if "FR3D_DB_PASSWORD" not in os.environ:
        raise ValueError(
            "Database credentials unavailable; set FR3D_DB_PASSWORD or use "
            "--env-file with a readable database.env"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DDatabase.ENV_FILE)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--run-id", type=int, action="append", default=[],
        help="simulation_runs.id to include; repeat to select runs (default: all completed)",
    )
    parser.add_argument("--unix-socket", help="optional local MariaDB socket path")
    args = parser.parse_args(argv)
    try:
        load_database_environment(args.env_file)
        from database.Database import connect
        from pymysql import MySQLError
    except (OSError, ValueError, ImportError) as error:
        print(f"poke_fr3d: {error}", file=sys.stderr)
        return 1

    try:
        markdown = generate_markdown(
            args.run_id,
            template_path=args.template,
            connection_factory=lambda: connect(
                database_name=DDatabase.SNAKE_LAB_DB_NAME,
                unix_socket=args.unix_socket,
            ),
        )
    except MySQLError:
        print(
            "poke_fr3d: could not read Snake Lab data; check database connectivity, "
            "credentials, schema, and SELECT privileges",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as error:
        print(f"poke_fr3d: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
