import uuid
from datetime import datetime
from uuid import UUID

import pytest
from server.auth.token_manager import KeycloakUserInfo
from server.constants import ORG_SETTINGS_VERSION
from server.verified_models.verified_model_service import (
    StoredVerifiedModel,  # noqa: F401
)
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

# Anything not loaded here may not have a table created for it.
from storage.api_key import ApiKey  # noqa: F401
from storage.base import Base
from storage.billing_session import BillingSession
from storage.conversation_work import ConversationWork
from storage.device_code import DeviceCode  # noqa: F401
from storage.feedback import Feedback
from storage.github_app_installation import GithubAppInstallation
from storage.org import Org
from storage.org_invitation import OrgInvitation  # noqa: F401
from storage.org_member import OrgMember
from storage.role import Role
from storage.stored_conversation_metadata import StoredConversationMetadata
from storage.stored_conversation_metadata_saas import (
    StoredConversationMetadataSaas,
)
from storage.stored_offline_token import StoredOfflineToken
from storage.stripe_customer import StripeCustomer
from storage.user import User


@pytest.fixture
def create_keycloak_user_info():
    """Fixture that returns a factory function to create KeycloakUserInfo models.

    Usage:
        def test_example(create_keycloak_user_info):
            user_info = create_keycloak_user_info(sub='user123', email='test@example.com')
    """

    def _create(**kwargs) -> KeycloakUserInfo:
        defaults = {
            'sub': 'test_user_id',
            'preferred_username': 'test_user',
        }
        defaults.update(kwargs)
        return KeycloakUserInfo(**defaults)

    return _create


# ---------------------------------------------------------------------------
# Session-scoped: one PostgreSQL container per xdist worker (= per process)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def _pg_container():
    """Start a PostgreSQL container for the test session."""
    with PostgresContainer('postgres:16-alpine') as pg:
        yield pg


@pytest.fixture(scope='session')
def _pg_template_db(_pg_container):
    """Create a template database with all tables via Base.metadata.create_all()."""
    pg = _pg_container
    host = pg.get_container_host_ip()
    port = pg.get_exposed_port(5432)
    user = pg.username
    password = pg.password
    dbname = pg.dbname

    # Connect to the default database and create the template
    default_url = f'postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}'
    default_engine = create_engine(default_url, isolation_level='AUTOCOMMIT')
    with default_engine.connect() as conn:
        conn.execute(text('CREATE DATABASE template_test'))
    default_engine.dispose()

    # Create all tables in the template database
    template_url = f'postgresql+psycopg2://{user}:{password}@{host}:{port}/template_test'
    template_engine = create_engine(template_url)
    Base.metadata.create_all(template_engine)
    template_engine.dispose()

    yield {
        'host': host,
        'port': port,
        'user': user,
        'password': password,
        'default_dbname': dbname,
    }


# ---------------------------------------------------------------------------
# Function-scoped: one cloned database per test
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def _test_db(_pg_template_db):
    """Clone the template database for a single test."""
    info = _pg_template_db
    db_name = f'test_{uuid.uuid4().hex[:12]}'
    default_url = (
        f"postgresql+psycopg2://{info['user']}:{info['password']}"
        f"@{info['host']}:{info['port']}/{info['default_dbname']}"
    )

    default_engine = create_engine(default_url, isolation_level='AUTOCOMMIT')
    with default_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}" TEMPLATE template_test'))
    default_engine.dispose()

    yield {**info, 'dbname': db_name}

    # Teardown: terminate connections then drop the test database
    default_engine = create_engine(default_url, isolation_level='AUTOCOMMIT')
    with default_engine.connect() as conn:
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    default_engine.dispose()


@pytest.fixture
def engine(_test_db):
    """Create a sync engine pointing at the per-test PostgreSQL database."""
    info = _test_db
    url = (
        f"postgresql+psycopg2://{info['user']}:{info['password']}"
        f"@{info['host']}:{info['port']}/{info['dbname']}"
    )
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
async def async_engine(_test_db):
    """Create an async engine pointing at the per-test PostgreSQL database."""
    info = _test_db
    url = (
        f"postgresql+asyncpg://{info['user']}:{info['password']}"
        f"@{info['host']}:{info['port']}/{info['dbname']}"
    )
    eng = create_async_engine(url)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_maker(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
async def async_session_maker(async_engine):
    """Create an async session maker bound to the async engine."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def add_minimal_fixtures(session_maker):
    with session_maker() as session:
        # Insert FK parent rows first: Org, Role, User
        session.add(
            Org(
                id=uuid.UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                name='mock-org',
                org_version=ORG_SETTINGS_VERSION,
                enable_default_condenser=True,
                enable_proactive_conversation_starters=True,
            )
        )
        session.add(
            Role(
                id=1,
                name='admin',
                rank=1,
            )
        )
        session.flush()
        session.add(
            User(
                id=uuid.UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                current_org_id=uuid.UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                user_consents_to_analytics=True,
            )
        )
        session.flush()

        # Now insert rows that depend on Org/Role/User
        session.add(
            OrgMember(
                org_id=uuid.UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                user_id=uuid.UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                role_id=1,
                llm_api_key='mock-api-key',
                status='active',
            )
        )
        session.add(
            StoredConversationMetadata(
                conversation_id='mock-conversation-id',
                created_at=datetime.fromisoformat('2025-03-07'),
                last_updated_at=datetime.fromisoformat('2025-03-08'),
                accumulated_cost=5.25,
                prompt_tokens=500,
                completion_tokens=250,
                total_tokens=750,
            )
        )
        session.flush()
        session.add(
            StoredConversationMetadataSaas(
                conversation_id='mock-conversation-id',
                user_id=UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
                org_id=UUID('5594c7b6-f959-4b81-92e9-b09c206f5081'),
            )
        )
        session.add(
            BillingSession(
                id='mock-billing-session-id',
                user_id='mock-user-id',
                status='completed',
                price=20,
                price_code='NA',
                created_at=datetime.fromisoformat('2025-03-03'),
                updated_at=datetime.fromisoformat('2025-03-04'),
            )
        )
        session.add(
            Feedback(
                id='mock-feedback-id',
                version='1.0',
                email='user@all-hands.dev',
                polarity='positive',
                permissions='public',
                trajectory=[],
            )
        )
        session.add(
            GithubAppInstallation(
                installation_id='mock-installation-id',
                encrypted_token='',
                created_at=datetime.fromisoformat('2025-03-05'),
                updated_at=datetime.fromisoformat('2025-03-06'),
            )
        )
        session.add(
            StoredOfflineToken(
                user_id='mock-user-id',
                offline_token='mock-offline-token',
                created_at=datetime.fromisoformat('2025-03-07'),
                updated_at=datetime.fromisoformat('2025-03-08'),
            )
        )
        session.add(
            StripeCustomer(
                keycloak_user_id='mock-user-id',
                stripe_customer_id='mock-stripe-customer-id',
                created_at=datetime.fromisoformat('2025-03-09'),
                updated_at=datetime.fromisoformat('2025-03-10'),
            )
        )
        session.add(
            ConversationWork(
                conversation_id='mock-conversation-id',
                user_id='mock-user-id',
                created_at=datetime.fromisoformat('2025-03-07'),
                updated_at=datetime.fromisoformat('2025-03-08'),
            )
        )
        session.commit()


@pytest.fixture
def session_maker_with_minimal_fixtures(engine):
    session_maker = sessionmaker(bind=engine)
    add_minimal_fixtures(session_maker)
    return session_maker
