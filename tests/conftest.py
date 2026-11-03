"""Pytest configuration and test fixtures."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///:memory:"

from app.db.base import Base
from app.main import app

# Synchronous SQLite engine for fast, in-memory testing
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionFactory = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test and drop after."""
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides a fresh isolated database session."""
    with TestSessionFactory() as session:
        yield session


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Synchronous test client for FastAPI."""
    with TestClient(app) as test_client:
        yield test_client
