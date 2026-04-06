from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnInfo:
    id: str
    name: str
    type: str
    role: str
    examples: list[Any] = field(default_factory=list)
    description: str = ""
    alias: list[str] = field(default_factory=list)
    table_id: str = ""
