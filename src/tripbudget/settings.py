from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIPBUDGET_", env_file=".env", extra="ignore")
    database_url: SecretStr = SecretStr("postgresql://tripbudget:tripbudget@127.0.0.1:55434/tripbudget")
    auth_mode: str = "local"
    firebase_project_id: str = ""
    firebase_allowed_uids: list[str] = []
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_url: str = "https://integrate.api.nvidia.com/v1"
    ollama_url: str = "http://127.0.0.1:11435"
    ollama_model: str = "tripbudget-gemma4-e4b"
    tailscale_proxy: str = ""
    tavily_api_key: SecretStr = SecretStr("")
    data_dir: Path = ROOT / "data"
    corpus_dir: Path = ROOT / "corpus"
    corpus_collection: str = "travel"
    embedding_cache: Path = ROOT / ".cache" / "embeddings"
    enable_test_controls: bool = False
    max_calls: int = Field(24, ge=1, le=24)
    max_attempts: int = Field(32, ge=1, le=32)
    max_tokens: int = Field(160000, ge=256, le=160000)
    max_output_tokens: int = Field(20000, ge=128, le=20000)
    active_seconds: int = Field(240, ge=1, le=240)
    provider_timeout: int = Field(45, ge=1, le=45)
    daily_episodes: int = 10
    evaluation_daily_episodes: int = 300
    session_hours: int = 8
    port: int = 8080
