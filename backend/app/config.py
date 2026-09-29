from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env",), extra="ignore")

    database_url: str = "postgresql+psycopg://fieldwatch:fieldwatch@localhost:5433/fieldwatch"
    firms_map_key: str = ""
    thresholds_path: Path = REPO_ROOT / "config" / "thresholds.yaml"
    owner: str = "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_thresholds() -> dict:
    return yaml.safe_load(get_settings().thresholds_path.read_text())
