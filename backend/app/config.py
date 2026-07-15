from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    gemini_api_key: str = ""
    nvidia_api_key: str = ""
    model_name: str = "gemini-3.1-flash-lite"
    # OpenAI-compatible endpoint the agents call. Defaults to the NVIDIA catalog
    # (the previous hardcoded value); point it at any compatible server —
    # e.g. LLM_BASE_URL=http://localhost:11434/v1 with MODEL_NAME=qwen2.5:7b runs
    # the whole investigation->debate->SAR pipeline on a local Ollama model with
    # no key and no data egress.
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    data_folder: Path = Path(__file__).resolve().parent.parent.parent / "data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "protected_namespaces": ("settings_",),
    }


settings = Settings()
