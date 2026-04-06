from dataclasses import dataclass, field


@dataclass
class MetricInfo:
    id: str
    name: str
    description: str
    relevant_columns: list[str] = field(default_factory=list)
    alias: list[str] = field(default_factory=list)
