from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    gemini_api_key: str = ""
    model_name: str = "gemini-2.5-flash"
    data_folder: Path = Path(__file__).resolve().parent.parent.parent / "data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "protected_namespaces": ("settings_",),
    }


settings = Settings()
