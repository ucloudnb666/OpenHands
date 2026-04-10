"""SQLAlchemy model for organization-member relationships."""

from pydantic import SecretStr
from sqlalchemy import JSON, UUID, Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from storage.base import Base
from storage.encrypt_utils import decrypt_value, encrypt_value


class OrgMember(Base):  # type: ignore
    """Junction table for organization-member relationships with roles."""

    __tablename__ = 'org_member'

    org_id = Column(UUID(as_uuid=True), ForeignKey('org.id'), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('user.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('role.id'), nullable=False)
    _llm_api_key = Column(String, nullable=False)
    has_custom_llm_api_key = Column(Boolean, nullable=False, default=False)
    agent_settings = Column(JSON, nullable=False, default=dict)
    conversation_settings = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=True)
    mcp_config = Column(JSON, nullable=True)

    org = relationship('Org', back_populates='org_members')
    user = relationship('User', back_populates='org_members')
    role = relationship('Role', back_populates='org_members')

    def __init__(self, **kwargs):
        for key in list(kwargs):
            if hasattr(self.__class__, key):
                setattr(self, key, kwargs.pop(key))

        if 'llm_api_key' in kwargs:
            self.llm_api_key = kwargs.pop('llm_api_key')

        if kwargs:
            raise TypeError(f'Unexpected keyword arguments: {list(kwargs.keys())}')

    @property
    def llm_api_key(self) -> SecretStr:
        return SecretStr(decrypt_value(self._llm_api_key))

    @llm_api_key.setter
    def llm_api_key(self, value: str | SecretStr):
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        self._llm_api_key = encrypt_value(raw)
