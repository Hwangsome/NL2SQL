import re


SAFE_SQL_PATTERN = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)


def ensure_safe_select(sql: str) -> None:
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Only a single SELECT statement is allowed.")
    if not SAFE_SQL_PATTERN.match(sql):
        raise ValueError("Only read-only SELECT SQL is allowed.")
