from typing import Final

from fr3d.constants.DFile import DFileDef as DEFFILE
from fr3d.constants.DField import DField as FIELD


class DOps:
    LLAMA_SERVER_PROCESS: Final[str] = DEFFILE.LLAMA_SERVER
    # Public MCP target; distinct from the llama-server executable name.
    LLM: Final[str] = "llm-server"
    OS: Final[str] = FIELD.OS
