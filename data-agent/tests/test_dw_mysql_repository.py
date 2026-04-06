import pytest

from app.core.sql_safety import ensure_safe_select


@pytest.mark.parametrize(
    ("sql", "expected_message"),
    [
        ("delete from fact_order", "Only read-only SELECT SQL is allowed."),
        ("select 1; select 2", "Only a single SELECT statement is allowed."),
    ],
)
def test_safe_select_guard(sql: str, expected_message: str):
    with pytest.raises(ValueError, match=expected_message):
        ensure_safe_select(sql)
