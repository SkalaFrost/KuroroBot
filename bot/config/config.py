from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int = 1
    API_HASH: str = ""
   
    
    FEED_AMOUNT: list = [10,20]
    MINE_AMOUNT: list = [10,20]
    SLEEP_TIME: list = [60,80]

    AUTO_UPGRADE: bool = True
    SAVE_COIN: int = 400_000

    AUTO_REINCARNATE: bool = True
    REINCARNATE_LVL: int = 70

    REF_ID: str = ''
    USE_PROXY_FROM_FILE: bool = False


settings = Settings()


