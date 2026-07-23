from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ManuscriptDocumentMetadataVersion,
    ManuscriptDocumentVersion,
    ManuscriptUnit,
    Project,
)
from .schemas import (
    ManuscriptDocumentVersionView,
    ManuscriptDocumentView,
    RestoreManuscriptDocument,
    SaveManuscriptDocument,
)


async def _owned_unit(
    db: AsyncSession, project_id: int, unit_id: int, user_id: int,
) -> ManuscriptUnit:
    unit = await db.scalar(
        select(ManuscriptUnit)
        .join(Project, Project.id == ManuscriptUnit.project_id)
        .where(
            ManuscriptUnit.id == unit_id,
            ManuscriptUnit.project_id == project_id,
            Project.owner_id == user_id,
        )
    )
    if unit is None:
        raise HTTPException(404, "正文单元不存在")
    return unit


async def _latest(
    db: AsyncSession, unit: ManuscriptUnit,
) -> ManuscriptDocumentVersion | None:
    return await db.scalar(
        select(ManuscriptDocumentVersion)
        .where(ManuscriptDocumentVersion.unit_id == unit.id)
        .order_by(ManuscriptDocumentVersion.version.desc())
        .limit(1)
    )


def _default_metadata(unit: ManuscriptUnit) -> dict:
    if unit.unit_type == "scene":
        return {"scene_heading": "内景", "location": "", "time_of_day": "", "characters": []}
    return {"pov_character": "", "narrative_person": "第三人称", "time_position": ""}


def _normalize_metadata(unit: ManuscriptUnit, value: dict) -> dict:
    defaults = _default_metadata(unit)
    return {key: value.get(key, default) for key, default in defaults.items()}


async def _metadata(db: AsyncSession, unit: ManuscriptUnit, version: int) -> dict:
    item = await db.scalar(select(ManuscriptDocumentMetadataVersion).where(
        ManuscriptDocumentMetadataVersion.unit_id == unit.id,
        ManuscriptDocumentMetadataVersion.version == version,
    ))
    return json.loads(item.metadata_json) if item else _default_metadata(unit)


def _view(version: ManuscriptDocumentVersion, metadata: dict) -> ManuscriptDocumentView:
    return ManuscriptDocumentView(
        unit_id=version.unit_id,
        project_id=version.project_id,
        version=version.version,
        content=version.content,
        source=version.source,
        metadata=metadata,
    )


async def get_document(
    db: AsyncSession, project_id: int, unit_id: int, user_id: int,
) -> ManuscriptDocumentView:
    unit = await _owned_unit(db, project_id, unit_id, user_id)
    version = await _latest(db, unit)
    if version is None:
        version = ManuscriptDocumentVersion(
            project_id=project_id,
            unit_id=unit.id,
            version=1,
            content=unit.adopted_content,
            source="adopted_baseline",
            created_by=user_id,
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)
    return _view(version, await _metadata(db, unit, version.version))


async def save_document(
    db: AsyncSession,
    project_id: int,
    unit_id: int,
    user_id: int,
    command: SaveManuscriptDocument,
    source: str = "manual_edit",
) -> ManuscriptDocumentView:
    unit = await _owned_unit(db, project_id, unit_id, user_id)
    if unit.status != "adopted":
        raise HTTPException(409, "只有已采用正文可以直接编辑；候选正文请先采用或拒绝")
    current = await _latest(db, unit)
    if current is None:
        current = ManuscriptDocumentVersion(
            project_id=project_id,
            unit_id=unit.id,
            version=1,
            content=unit.adopted_content,
            source="adopted_baseline",
            created_by=user_id,
        )
        db.add(current)
        await db.flush()
    if command.base_version != current.version:
        raise HTTPException(
            409,
            {"message": "正文已在其他位置更新，请重新载入后比较", "current_version": current.version},
        )
    current_metadata = await _metadata(db, unit, current.version)
    next_metadata = _normalize_metadata(unit, command.metadata or current_metadata)
    if command.content == current.content and next_metadata == current_metadata:
        return _view(current, current_metadata)
    saved = ManuscriptDocumentVersion(
        project_id=project_id,
        unit_id=unit.id,
        version=current.version + 1,
        content=command.content,
        source=source,
        created_by=user_id,
    )
    db.add(saved)
    db.add(ManuscriptDocumentMetadataVersion(
        project_id=project_id, unit_id=unit.id, version=current.version + 1,
        metadata_json=json.dumps(next_metadata, ensure_ascii=False), created_by=user_id,
    ))
    unit.adopted_content = command.content
    await db.commit()
    await db.refresh(saved)
    return _view(saved, next_metadata)


async def list_document_versions(
    db: AsyncSession, project_id: int, unit_id: int, user_id: int,
) -> list[ManuscriptDocumentVersionView]:
    unit = await _owned_unit(db, project_id, unit_id, user_id)
    await get_document(db, project_id, unit.id, user_id)
    versions = (await db.scalars(
        select(ManuscriptDocumentVersion)
        .where(ManuscriptDocumentVersion.unit_id == unit.id)
        .order_by(ManuscriptDocumentVersion.version.desc())
    )).all()
    return [ManuscriptDocumentVersionView(
        version=version.version, content=version.content, source=version.source,
        metadata=await _metadata(db, unit, version.version),
    ) for version in versions]


async def restore_document_version(
    db: AsyncSession,
    project_id: int,
    unit_id: int,
    user_id: int,
    command: RestoreManuscriptDocument,
) -> ManuscriptDocumentView:
    await _owned_unit(db, project_id, unit_id, user_id)
    target = await db.scalar(select(ManuscriptDocumentVersion).where(
        ManuscriptDocumentVersion.unit_id == unit_id,
        ManuscriptDocumentVersion.version == command.restore_version,
    ))
    if target is None:
        raise HTTPException(404, "要恢复的正文版本不存在")
    return await save_document(
        db,
        project_id,
        unit_id,
        user_id,
        SaveManuscriptDocument(
            base_version=command.base_version,
            content=target.content,
            metadata=await _metadata(db, await _owned_unit(db, project_id, unit_id, user_id), target.version),
        ),
        source=f"restore_v{command.restore_version}",
    )
