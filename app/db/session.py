from sqlmodel import Session, create_engine, select

from app.api.user import user_service
from app.core.config import settings

# Configure engine with connection pool and SSL settings
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    connect_args={
        "sslmode": settings.POSTGRES_SSL_MODE,
        "connect_timeout": 10,
    },
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,  # Recycle connections after 1 hour
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    from app.api.user.user_model import Role, User
    from app.api.user.user_schema import UserCreate

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
            role=Role.ADMIN,
        )
        user = user_service.create_user(session=session, user_create=user_in)
