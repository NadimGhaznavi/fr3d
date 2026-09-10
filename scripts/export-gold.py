#!/usr/bin/env python3
"""Export the current seed's best completed configuration as JSON."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymysql import MySQLError

from dialogue.poke_fr3d import load_database_environment
from fr3d.app.whole_config.configuration import Configuration
from fr3d.app.whole_config.store import SearchStore
from fr3d.constants.DDatabase import DDatabase
from fr3d.database.DbMgr import DbMgr


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write JSON to this file (default: stdout)')
    parser.add_argument('--env-file', type=Path, default=DDatabase.ENV_FILE,
                        help='database credentials file (default: %(default)s)')
    parser.add_argument('--unix-socket', help='optional local MariaDB socket path')
    args = parser.parse_args(argv)
    try:
        load_database_environment(args.env_file)
        store = SearchStore(Configuration(), connection_factory=lambda: DbMgr.connect(
            database_name=DDatabase.SNAKE_LAB_DB_NAME, unix_socket=args.unix_socket))
        gold = store.gold()
        content = json.dumps(gold['config'], indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(content, encoding='utf-8')
        else:
            sys.stdout.write(content)
        print(f'Exported gold run {gold["run_id"]}, seed {gold["config"]["seed"]}, '
              f'high score {gold["high_score"]}.', file=sys.stderr)
    except MySQLError:
        print('Could not read Snake Lab data; check database credentials and connectivity.', file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
