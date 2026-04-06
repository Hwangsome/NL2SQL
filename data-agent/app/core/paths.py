from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
