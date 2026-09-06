from pathlib import Path
from typing import Final

from fr3d.constants.DDir import DDirDef as DEFDIR
from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DField import DField as FIELD

class DDatabase:
    ENV_FILE: Final[Path] = DEFDIR.CONFIG / DEFFILE.DATABASE_ENV
    HOST: Final[str] = FIELD.LOCALHOST
    PORT: Final[int] = 3306
    DB_NAME: Final[str] = "fr3d"
    USERNAME: Final[str] = "fr3d"
    SNAKE_LAB_DB_NAME: Final[str] = FIELD.SNAKELAB
