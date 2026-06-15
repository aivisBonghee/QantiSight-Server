from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ibonghui@localhost:5432/qantisight"

    ai_model_url: str = "http://localhost:8888"
    ai_model_upload_base: str = "/data"

    data_server_host: str = ""
    data_server_port: int = 22
    data_server_user: str = ""
    data_server_password: str = ""
    data_server_ssh_key: str = ""
    data_server_path: str = "/mnt/QantiSight"

    class Config:
        env_file = ".env"


settings = Settings()
