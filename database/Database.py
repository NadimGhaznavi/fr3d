"""Create configured MariaDB connections for Fr3d services."""

from __future__ import annotations

import os

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from constants.DDatabase import DDatabase

class DbManager:

    def __init__(self) -> None:
        pass

    def connect(
        *, database_name: str | None = None, unix_socket: str | None = None
    ) -> Connection:
        """Connect as the installer-provisioned Fr3d database account."""
        return pymysql.connect(
            host=os.getenv("FR3D_DB_HOST", DDatabase.HOST),
            port=int(os.getenv("FR3D_DB_PORT", str(DDatabase.PORT))),
            user=os.getenv("FR3D_DB_USER", DDatabase.USERNAME),
            password=os.environ["FR3D_DB_PASSWORD"],
            database=(
                database_name
                if database_name is not None
                else os.getenv("FR3D_DB_NAME", DDatabase.DB_NAME)
            ),
            unix_socket=unix_socket,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=DictCursor,
        )
