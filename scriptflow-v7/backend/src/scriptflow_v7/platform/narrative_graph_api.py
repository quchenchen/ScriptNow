from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, Header, HTTPException, status
from sqlalchemy import select

from scriptflow_v7.platform.auth import AuthenticationFailed, AuthService, CsrfFailed
from scriptflow_v7.platform.auth_api import ACCESS_COOKIE
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    NarrativeEdgeModel,
    NarrativeIndexModel,
    NarrativeIndexStatus,
    NarrativeNodeModel,
    NarrativeTextUnitModel,
    ProjectMedium,
    ProjectModel,
    WorkspaceFileModel,
)
from scriptflow_v7.platform.narrative_graph_extractor import NarrativeGraphExtractor
from scriptflow_v7.platform.narrative_graph_schema import (
    canonical_node_type,
    canonical_relation_type,
)


def create_narrative_graph_router(
    database: Database, auth: AuthService, settings: Settings
) -> APIRouter:
    router = APIRouter(prefix="/novel/projects/{project_id}/narrative-graph", tags=["novel-graph"])
    extractor = NarrativeGraphExtractor(database, settings)

    async def tenant_id(access_token: str | None) -> str:
        if access_token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            return str((await auth.validate_access(access_token)).tenant_id)
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    async def write_tenant_id(access_token: str | None, csrf_token: str | None) -> str:
        if access_token is None or csrf_token is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf token required")
        try:
            return str((await auth.authorize_action(access_token, csrf_token)).tenant_id)
        except CsrfFailed as error:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "csrf validation failed") from error
        except AuthenticationFailed as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required") from error

    @router.get("")
    async def graph(
        project_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        current_tenant = await tenant_id(access_token)
        async with database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != current_tenant
                or project.medium != ProjectMedium.NOVEL
            ):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Novel project not found")
            index = (
                await session.scalars(
                    select(NarrativeIndexModel)
                    .where(
                        NarrativeIndexModel.tenant_id == current_tenant,
                        NarrativeIndexModel.project_id == project_id,
                        NarrativeIndexModel.status == NarrativeIndexStatus.READY,
                    )
                    .order_by(NarrativeIndexModel.version.desc())
                )
            ).first()
            if index is None:
                return {"status": "not_built", "chapters": [], "nodes": [], "edges": []}
            source = await session.get(WorkspaceFileModel, index.source_file_id)
            units = list(
                await session.scalars(
                    select(NarrativeTextUnitModel)
                    .where(NarrativeTextUnitModel.index_id == index.id)
                    .order_by(NarrativeTextUnitModel.ordinal)
                )
            )
            stored_nodes = list(
                await session.scalars(
                    select(NarrativeNodeModel).where(NarrativeNodeModel.index_id == index.id)
                )
            )
            stored_edges = list(
                await session.scalars(
                    select(NarrativeEdgeModel).where(NarrativeEdgeModel.index_id == index.id)
                )
            )

        chapters: OrderedDict[str, dict[str, object]] = OrderedDict()
        units_by_id = {unit.id: unit for unit in units}
        for unit in units:
            if unit.chapter_key == "front-matter":
                continue
            item = chapters.setdefault(
                unit.chapter_key,
                {
                    "id": unit.chapter_key,
                    "type": "chapter",
                    "label": unit.chapter_title,
                    "summary": "",
                    "unit_count": 0,
                    "evidence": [],
                },
            )
            item["unit_count"] = int(item["unit_count"]) + 1
            item["evidence"].append({"unit_id": unit.id, "label": unit.contextual_header})

        node_rows = [
            {
                "id": node.id,
                "type": canonical_node_type(node.node_type).value,
                "label": node.name,
                "summary": node.description,
                "chapters": sorted(
                    {
                        units_by_id[unit_id].chapter_title
                        for unit_id in node.evidence_unit_ids
                        if unit_id in units_by_id
                        and units_by_id[unit_id].chapter_key != "front-matter"
                    }
                ),
                "evidence_count": len(node.evidence_unit_ids),
                "evidence": [
                    {
                        "unit_id": unit_id,
                        "label": units_by_id[unit_id].contextual_header,
                    }
                    for unit_id in node.evidence_unit_ids
                    if unit_id in units_by_id
                ],
            }
            for node in stored_nodes
        ]
        if not node_rows:
            node_rows = list(chapters.values())
        edge_rows = [
            {
                "id": edge.id,
                "type": canonical_relation_type(edge.edge_type).value,
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "label": edge.description,
                "inference": edge.inference,
            }
            for edge in stored_edges
        ]
        if not edge_rows:
            chapter_ids = list(chapters)
            edge_rows = [
                {
                    "id": f"chapter-flow-{position}",
                    "type": "chapter_flow",
                    "source": chapter_ids[position],
                    "target": chapter_ids[position + 1],
                    "label": "章节推进",
                    "inference": False,
                }
                for position in range(len(chapter_ids) - 1)
            ]
        return {
            "status": "ready" if stored_nodes else "structure_ready",
            "extraction_status": dict(index.config).get("extraction_status", "not_started"),
            "extraction_progress": {
                "completed": int(dict(index.config).get("extraction_completed", 0)),
                "total": int(dict(index.config).get("extraction_total", len(chapters))),
            },
            "index": {
                "version": index.version,
                "source_name": source.original_name if source else "创作素材",
            },
            "chapters": list(chapters.values()),
            "nodes": node_rows,
            "edges": edge_rows,
        }

    @router.post("/extract", status_code=status.HTTP_202_ACCEPTED)
    async def extract(
        project_id: str,
        background_tasks: BackgroundTasks,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, str]:
        current_tenant = await write_tenant_id(access_token, csrf_token)
        async with database.session() as session:
            index = (
                await session.scalars(
                    select(NarrativeIndexModel)
                    .where(
                        NarrativeIndexModel.tenant_id == current_tenant,
                        NarrativeIndexModel.project_id == project_id,
                        NarrativeIndexModel.status == NarrativeIndexStatus.READY,
                    )
                    .order_by(NarrativeIndexModel.version.desc())
                )
            ).first()
            if index is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "请先完成素材解析，再构建故事图谱。")
            if dict(index.config).get("extraction_status") == "running":
                return {"status": "running"}
            index.config = {**dict(index.config), "extraction_status": "queued"}
            index_id = index.id
        background_tasks.add_task(
            extractor.extract,
            tenant_id=current_tenant,
            project_id=project_id,
            index_id=index_id,
        )
        return {"status": "queued"}

    @router.get("/evidence/{unit_id}")
    async def evidence(
        project_id: str,
        unit_id: str,
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    ) -> dict[str, object]:
        current_tenant = await tenant_id(access_token)
        async with database.session() as session:
            unit = await session.get(NarrativeTextUnitModel, unit_id)
            if unit is None or unit.tenant_id != current_tenant or unit.project_id != project_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
            return {
                "chapter": unit.chapter_title,
                "label": unit.contextual_header,
                "excerpt": unit.content[:800],
            }

    return router
