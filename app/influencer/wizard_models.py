"""Pydantic schemas para el wizard de creación de personas — TASK-INFLU-009.

Cada paso del wizard valida y persiste un sub-JSONB de
``influencer.personas`` (``face``, ``body``, ``identity``, ``voice``,
``platforms``).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─── Paso 1 — Cara ─────────────────────────────────────────────────────────


StartingPoint = Literal['upload', 'template', 'random']
EyeColor = Literal['brown', 'black', 'blue', 'green', 'hazel', 'gray', 'amber']
HairColor = Literal['black', 'brown', 'blonde', 'red', 'gray', 'white', 'colored']
HairStyle = Literal['short', 'medium', 'long', 'curly', 'wavy', 'straight', 'shaved']
SkinTone = Literal['light', 'medium-light', 'medium', 'medium-dark', 'dark']
AgeRange = Literal['18-24', '25-34', '35-44', '45-54', '55+']


class FaceStep(BaseModel):
    starting_point: StartingPoint
    ethnicity: str = Field(..., min_length=1, max_length=64)
    eye_color: EyeColor
    hair_color: HairColor
    hair_style: HairStyle
    skin_tone: SkinTone
    age_range: AgeRange
    variations: int = Field(default=4, ge=1, le=10)


# ─── Paso 2 — Cuerpo ───────────────────────────────────────────────────────


Silhouette = Literal['slim', 'athletic', 'curvy', 'average']
Posture = Literal['confident', 'casual', 'elegant', 'sporty']


class BodyStep(BaseModel):
    silhouette: Silhouette
    height_cm: int = Field(..., ge=140, le=210)
    posture: Posture


# ─── Paso 3 — Identidad ────────────────────────────────────────────────────


_HANDLE_RE = re.compile(r'^[a-z0-9][a-z0-9_]{2,29}$')


class IdentityStep(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    handle: str = Field(..., min_length=3, max_length=30)
    age: int = Field(..., ge=18, le=99)
    city: str = Field(..., min_length=1, max_length=80)
    country: str = Field(..., min_length=2, max_length=80)
    languages: list[str] = Field(default_factory=list, max_length=8)
    brands: list[str] = Field(default_factory=list, max_length=20)
    categories: list[str] = Field(default_factory=list, max_length=10)
    description: str = Field(default='', max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator('handle')
    @classmethod
    def _normalize_handle(cls, value: str) -> str:
        v = value.strip().lower()
        if not _HANDLE_RE.match(v):
            raise ValueError(
                'handle must match [a-z0-9][a-z0-9_]{2,29} after lowercase',
            )
        return v


# ─── Paso 4 — Voz ──────────────────────────────────────────────────────────


VoiceTone = Literal['warm', 'close', 'aspirational', 'energetic', 'calm', 'playful']
Formality = Literal['informal', 'neutral', 'formal']


class VoiceStep(BaseModel):
    tone: VoiceTone
    formality: Formality = 'neutral'
    energy_level: int = Field(default=5, ge=1, le=10)
    voice_id_ref: str | None = Field(default=None, max_length=80)


# ─── Paso 5 — Plataformas ──────────────────────────────────────────────────


PlatformName = Literal['instagram', 'tiktok', 'facebook', 'youtube', 'x']
PostingMode = Literal['auto_generate', 'manual_approval', 'hybrid']


class PlatformAccount(BaseModel):
    platform: PlatformName
    handle: str = Field(..., min_length=1, max_length=64)
    posts_per_week: int = Field(default=3, ge=0, le=50)


class PlatformsStep(BaseModel):
    accounts: list[PlatformAccount] = Field(default_factory=list, max_length=10)
    mode: PostingMode = 'manual_approval'
    auto_respond_dms: bool = False
    disclose_ai: bool = True


__all__ = [
    'StartingPoint',
    'FaceStep',
    'BodyStep',
    'IdentityStep',
    'VoiceStep',
    'PlatformsStep',
    'PlatformAccount',
]
