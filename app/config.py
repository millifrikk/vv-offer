from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./data/vv_offer.db"
    upload_dir: Path = Path("./data/uploads")
    output_dir: Path = Path("./data/outputs")
    app_title: str = "VV Offer Tool"
    secret_key: str = "change-me-in-production"
    admin_email: str = "emil@vatnsvirkinn.is"
    admin_password: str = "testVV123"
    user_password: str = "testVV123"
    session_max_age: int = 604800  # 7 days

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_dirs(self):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> str:
        return self.database_url.replace("sqlite:///", "")


settings = Settings()
