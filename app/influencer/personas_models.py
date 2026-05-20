"""Pydantic models para personas endpoints — TASK-INFLU-008.

Cada modelo refleja exactamente las columnas/jsonb de la tabla
``influencer.personas``. Los jsonb (face/body/identity/voice/platforms)
se modelan como ``dict[str, Any]`` — las shapes detalladas se validan
en TASK-INFLU-009 (wizard endpoints) donde cada paso tiene su schema.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


PersonaStatus = Literal['draft', 'active', 'paused', 'archived']
PersonaMode = Literal['auto_generate', 'manual_approval', 'hybrid']

_HANDLE_RE = re.compile(r'^[a-z0-9][a-z0-9_]{2,29}$')


class PersonaBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    handle: str = Field(..., min_length=3, max_length=30)
    status: PersonaStatus = 'draft'
    category: str | None = Field(default=None, max_length=64)
    face: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)
    identity: dict[str, Any] = Field(default_factory=dict)
    voice: dict[str, Any] = Field(default_factory=dict)
    platforms: dict[str, Any] = Field(default_factory=dict)
    mode: PersonaMode = 'manual_approval'
    disclose_ai: bool = True

    @field_validator('handle')
    @classmethod
    def _normalize_handle(cls, value: str) -> str:
        v = value.strip().lower()
        if not _HANDLE_RE.match(v):
            raise ValueError(
                'handle must be lowercase alnum/underscore, 3-30 chars, '
                'starting with a letter or digit',
            )
        return v


class PersonaCreate(PersonaBase):
    """Cuerpo del POST /v1/influencer/personas. status forzado a 'draft'."""
    status: PersonaStatus = 'draft'


class PersonaUpdate(BaseModel):
    """Cuerpo del PATCH — todos los campos opcionales."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    handle: str | None = Field(default=None, min_length=3, max_length=30)
    status: PersonaStatus | None = None
    category: str | None = Field(default=None, max_length=64)
    face: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    identity: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    platforms: dict[str, Any] | None = None
    mode: PersonaMode | None = None
    disclose_ai: bool | None = None

    @field_validator('handle')
    @classmethod
    def _normalize_handle(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        if not _HANDLE_RE.match(v):
            raise ValueError('handle must match [a-z0-9][a-z0-9_]{2,29}')
        return v


class PersonaResponse(PersonaBase):
    """Shape devuelto en GET / POST / PATCH responses."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    archived_at: datetime | None = None


class PersonasList(BaseModel):
    items: list[PersonaResponse]
    total: int


__all__ = [
    'PersonaStatus',
    'PersonaMode',
    'PersonaBase',
    'PersonaCreate',
    'PersonaUpdate',
    'PersonaResponse',
    'PersonasList',
]
