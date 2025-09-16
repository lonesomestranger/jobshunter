from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    search_type = Column(String, nullable=False, default="rabota_by")
    search_params = Column(JSON, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    user = relationship("User", back_populates="subscriptions")

    vacancies = relationship(
        "Vacancy", back_populates="subscription", cascade="all, delete-orphan"
    )
    dork_results = relationship(
        "DorkResult", back_populates="subscription", cascade="all, delete-orphan"
    )


class Vacancy(Base):
    __tablename__ = "vacancies"
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    salary = Column(String)
    location = Column(String)
    description = Column(String)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    subscription = relationship("Subscription", back_populates="vacancies")

    __table_args__ = (
        UniqueConstraint("url", "subscription_id", name="uq_vacancy_url_subscription"),
    )


class DorkResult(Base):
    __tablename__ = "dork_results"
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)
    title = Column(String)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    subscription = relationship("Subscription", back_populates="dork_results")

    __table_args__ = (
        UniqueConstraint("url", "subscription_id", name="uq_dork_url_subscription"),
    )
