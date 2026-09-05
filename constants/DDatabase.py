from pathlib import Path
from typing import Final


class DDatabase:
    ENV_FILE: Final[Path] = Path("/etc/fr3d/database.env")
    HOST: Final[str] = "localhost"
    PORT: Final[int] = 3306
    DB_NAME: Final[str] = "fr3d"
    USERNAME: Final[str] = "fr3d"
    SNAKE_LAB_DB_NAME: Final[str] = "snakelab"
