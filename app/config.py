import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return os.environ.get(
            "DATABASE_URL",
            "mysql+pymysql://{user}:{password}@{host}:{port}/{name}".format(
                user=os.environ.get("DB_USER", "accntbl"),
                password=os.environ.get("DB_PASSWORD", "accntbl"),
                host=os.environ.get("DB_HOST", "db"),
                port=os.environ.get("DB_PORT", "3306"),
                name=os.environ.get("DB_NAME", "accntbl"),
            ),
        )


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(Config):
    pass


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name=None):
    env_name = env_name or os.environ.get("FLASK_ENV", "development")
    return CONFIG_BY_NAME.get(env_name, DevelopmentConfig)
