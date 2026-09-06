"""Create configured MariaDB connections for Fr3d services."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from fr3d.constants.DDatabase import DDatabase

class DbMgr:

    def __init__(self, *, database_name: str | None = None, unix_socket: str | None = None):
        self.database_name = database_name
        self.unix_socket = unix_socket

    @contextmanager
    def transaction(self):
        """Use one connection per transaction; commit or roll back, then close."""
        connection = self.connect(database_name=self.database_name, unix_socket=self.unix_socket)
        try:
            yield DbSession(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query(self, sql: str, parameters: tuple = ()) -> list[dict[str, Any]]:
        with self.transaction() as session:
            return session.query(sql, parameters)

    @staticmethod

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


class DbSession:
    """Parameterized SQL execution within a DbMgr-owned transaction."""

    def __init__(self, connection: Connection):
        self.connection = connection

    def query(self, sql: str, parameters: tuple = ()) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return list(cursor.fetchall())

    def insert(self, sql: str, parameters: tuple = ()) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return int(cursor.lastrowid)
