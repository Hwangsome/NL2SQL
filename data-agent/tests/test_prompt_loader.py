from app.prompt.prompt_loader import load_prompt


def test_prompt_loads():
    prompt = load_prompt("generate_sql")
    assert prompt
    assert "SELECT" in prompt or "SQL" in prompt
