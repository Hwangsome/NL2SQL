from pathlib import Path

def load_prompt(name: str) -> str:
    prompt_path = Path(__file__).parents[2] / "prompts" / f"{name}.prompt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8").strip()
