from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# The `DATABASE_URL` variable is storing the connection string or URL used to connect to a PostgreSQL
# database. In this case, the URL contains information such as the username, password, host, port,
# database name, and additional parameters like channel binding and SSL mode required for establishing
# a secure connection to the database. This URL is then used by the `create_engine` function from
# SQLAlchemy to create an engine that will handle the connection to the specified PostgreSQL database.
DATABASE_URL = "postgresql://neondb_owner:npg_yM4wdDI8iCER@ep-weathered-haze-aoxq7dku-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()