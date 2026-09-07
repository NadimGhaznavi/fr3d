#!/usr/bin/env python3
"""List every Snake Lab experiment's ID, high score, and learning rate."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymysql import MySQLError, connect
from pymysql.cursors import DictCursor

from fr3d.constants.DDatabase import DDatabase


def render_table(rows):
    table = [["ID", "High score", "LR"]]
    for row in rows:
        config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        rate = (config or {}).get("training", {}).get("learning_rate")
        table.append([str(row["id"]),
                      "N/A" if row["high_score"] is None else str(row["high_score"]),
                      "N/A" if rate is None else str(rate)])
    widths = [max(len(row[column]) for row in table) for column in range(3)]
    lines = ["  ".join(value.rjust(width) for value, width in zip(row, widths)) for row in table]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines) + f"\n\n{len(rows)} experiments\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unix-socket", default="/run/mysqld/mysqld.sock",
                        help="local MariaDB socket path (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        connection = connect(user="root", password="",
                             database=DDatabase.SNAKE_LAB_DB_NAME,
                             unix_socket=args.unix_socket,
                             charset="utf8mb4", cursorclass=DictCursor)
        try:
            with connection.cursor() as cursor:
                # Include every status, including experiments without a score yet.
                cursor.execute("SELECT id, high_score, config FROM simulation_runs ORDER BY score")
                rows = cursor.fetchall()
        finally:
            connection.close()
        print(render_table(rows), end="")
    except MySQLError:
        print("Could not read Snake Lab data as root; check the socket path and run with sudo "
              "if root uses Unix socket authentication.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
