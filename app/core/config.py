from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tripio AI"
    app_env: str = "local"
    spring_boot_api_base_url: str = "http://localhost:8080/api"
    database_url: str = "postgresql+psycopg://tripio:tripio@localhost:5432/tripio"
    kakao_rest_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    tour_api_service_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
