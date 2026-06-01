import os
from pydantic import BaseModel

class Settings(BaseModel):
    secret_key: str = "9a8d7c6b5a4d3c2b1a0f9e8d7c6b5a4d3c2b1a0f9e8d7c6b5a4d3c2b1a0f9e8d"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./sql_app.db"
    openai_api_key: str = ""

    @classmethod
    def load(cls):
        # Load values from environment variables if present
        # Pydantic v2: use model_fields instead of __fields__
        fields = cls.model_fields
        env = {
            "secret_key": os.getenv("SECRET_KEY", fields["secret_key"].default),
            "algorithm": os.getenv("ALGORITHM", fields["algorithm"].default),
            "access_token_expire_minutes": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", fields["access_token_expire_minutes"].default)),
            "database_url": os.getenv("DATABASE_URL", fields["database_url"].default),
            "openai_api_key": os.getenv("OPENAI_API_KEY", fields["openai_api_key"].default),
        }
        return cls(**env)

settings = Settings.load()
