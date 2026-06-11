"""ACP configuration schema."""

from pydantic import BaseModel, Field
from typing import List, Dict


class ACPConfig(BaseModel):
    """Configuration for an ACP backend (e.g. Cursor, Claude)."""
    backend: str = Field(..., description="Backend type: cursor, claude, etc.")
    command: List[str] = Field(..., description="Command and base args to launch the backend")
    args: List[str] = Field(default_factory=list, description="Additional arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables for the process")
    auto_restart: bool = Field(default=True, description="Whether to auto-restart on crash")
    restart_delay: float = Field(default=1.0, description="Delay before restart in seconds")
