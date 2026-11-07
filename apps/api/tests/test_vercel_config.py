import json
from pathlib import Path


CONFIG = Path(__file__).parents[1] / "vercel.json"


def test_api_vercel_config_uses_one_bounded_fastapi_function_without_secrets():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert config["functions"] == {"app/main.py": {"maxDuration": 60}}
    assert "env" not in config
    assert "builds" not in config
