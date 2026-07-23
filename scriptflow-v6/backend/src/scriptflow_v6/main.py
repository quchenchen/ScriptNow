from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_runtime import creative_runtime
from .cascade_revisions import list_cascade_revisions, resolve_cascade_revision
from .continuity import continuity_view
from .medium_profiles import profile_labels
from .story_architecture import get_architecture, plan_architecture, update_arc
from .story_structures import structure_labels
from .continuity_ledger import (
    create_entity,
    create_foreshadow,
    create_relationship,
    list_foreshadows,
    list_relationships,
    transition_foreshadow,
)
from .db import engine, session
from .directives import create_directive, list_directives
from .living_assets import list_candidates, resolve_candidate
from .manuscript_documents import (
    get_document,
    list_document_versions,
    restore_document_version,
    save_document,
)
from .manuscript_edits import create_edit, persist_prepared_edit, prepare_edit, resolve_edit
from .manuscript_impacts import list_impact_candidates, resolve_impact_candidate
from .models import Base
from .project_planning import (
    add_story_map_unit,
    apply_plan_change,
    get_plan,
    get_story_map,
    preview_plan_change,
    reorder_story_map_units,
    update_story_map_unit,
)
from .projects import (
    adopt_candidate,
    create_project,
    demo_user,
    list_projects,
    project_view,
    run_task,
)
from .revisions import create, resolve
from .runtime_config import runtime_config
from .schemas import (
    CascadeRevisionView,
    ContextPreviewView,
    ContinuityView,
    CreateCharacterIntroduction,
    CreateDirective,
    CreateForeshadow,
    CreateForeshadowPlanChange,
    CreateManuscriptAiEdit,
    CreateNarrativeEntity,
    CreateProject,
    CreateRelationshipChange,
    CreateRevision,
    CreateStoryMapUnit,
    CreateWorldRuleChange,
    DirectiveView,
    ForeshadowTransition,
    ForeshadowView,
    LivingAssetCandidateView,
    ManuscriptDocumentVersionView,
    ManuscriptDocumentView,
    ManuscriptEditRevisionView,
    ManuscriptImpactCandidateView,
    ManuscriptUnitView,
    NarrativeEntityView,
    NarrativeRelationshipCommand,
    NarrativeRelationshipView,
    ProjectPlanChange,
    ProjectPlanImpactView,
    ProjectPlanView,
    ProjectView,
    ReorderStoryMapUnits,
    RestoreManuscriptDocument,
    RevisionView,
    RuntimeStatusView,
    RuntimeTestView,
    SaveManuscriptDocument,
    StoryBibleChangeView,
    StoryMapUnitUpdate,
    StoryMapUnitView,
    StoryMapView,
    TaskView,
)
from .story_bible_changes import (
    create_character_introduction,
    create_foreshadow_plan_change,
    create_relationship_change,
    create_world_rule_change,
    list_changes,
    resolve_change,
)
from .writing import (
    adopt_manuscript,
    draft_opening,
    get_latest_unit,
    get_manuscript_unit,
    get_opening,
    preview_next_context,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="ScriptFlow V6", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5174", "http://localhost:5174", "http://localhost:5175", "http://127.0.0.1:5175"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "v6"}


@app.get("/runtime/status", response_model=RuntimeStatusView)
async def runtime_status():
    configured = runtime_config.configured or bool(os.getenv("DASHSCOPE_API_KEY") or os.getenv("SCRIPTFLOW_API_KEY"))
    return RuntimeStatusView(mode="platform" if configured else "demo", available=True,
        capability_tier="专业创作" if configured else "流程演示")


@app.post("/runtime/test", response_model=RuntimeTestView)
async def test_runtime():
    runtime = creative_runtime()
    if runtime.name == "mock":
        return RuntimeTestView(ok=False, runtime="mock", model=runtime_config.model, message="尚未配置真实模型")
    try:
        drafts = await runtime.shape_story_cores(
            title="连通性检查", goal_type="original-novel", seed="一个人必须在今天做出选择", source_text="")
        return RuntimeTestView(ok=len(drafts) == 3, runtime=runtime.name, model=runtime_config.model,
            message="模型已返回结构化 Story Core" if len(drafts) == 3 else "模型返回数量不正确")
    except Exception as exc:
        return RuntimeTestView(ok=False, runtime=runtime.name, model=runtime_config.model,
            message=f"模型调用失败：{type(exc).__name__}")


@app.post("/projects", response_model=ProjectView)
async def new_project(command: CreateProject, db: AsyncSession = Depends(session)):
    return await create_project(db, command)


@app.get("/projects", response_model=list[ProjectView])
async def get_projects(db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_projects(db, user.id)


@app.get("/projects/{project_id}", response_model=ProjectView)
async def get_project(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await project_view(db, project_id, user.id)


@app.get(
    "/projects/{project_id}/manuscript/units/{unit_id}/document",
    response_model=ManuscriptDocumentView,
)
async def read_manuscript_document(
    project_id: int, unit_id: int, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await get_document(db, project_id, unit_id, user.id)


@app.put(
    "/projects/{project_id}/manuscript/units/{unit_id}/document",
    response_model=ManuscriptDocumentView,
)
async def put_manuscript_document(
    project_id: int, unit_id: int, command: SaveManuscriptDocument,
    db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await save_document(db, project_id, unit_id, user.id, command)


@app.get(
    "/projects/{project_id}/manuscript/units/{unit_id}/document/versions",
    response_model=list[ManuscriptDocumentVersionView],
)
async def read_manuscript_document_versions(
    project_id: int, unit_id: int, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await list_document_versions(db, project_id, unit_id, user.id)


@app.post(
    "/projects/{project_id}/manuscript/units/{unit_id}/document/restore",
    response_model=ManuscriptDocumentView,
)
async def restore_manuscript_document(
    project_id: int, unit_id: int, command: RestoreManuscriptDocument,
    db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await restore_document_version(db, project_id, unit_id, user.id, command)


@app.post(
    "/projects/{project_id}/manuscript/units/{unit_id}/ai-edits",
    response_model=ManuscriptEditRevisionView,
)
async def create_manuscript_ai_edit(
    project_id: int, unit_id: int, command: CreateManuscriptAiEdit,
    db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await create_edit(db, project_id, unit_id, user.id, command)


@app.post("/projects/{project_id}/manuscript/units/{unit_id}/ai-edits/stream")
async def stream_manuscript_ai_edit(
    project_id: int,
    unit_id: int,
    command: CreateManuscriptAiEdit,
    request: Request,
    db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    prepared = await prepare_edit(db, project_id, unit_id, user.id, command)
    replacement = prepared["draft"].replacement_text

    async def events():
        yield json.dumps({"type": "started", "base_version": command.base_version}, ensure_ascii=False) + "\n"
        chunk_size = 24
        for start in range(0, len(replacement), chunk_size):
            if await request.is_disconnected():
                return
            yield json.dumps({"type": "delta", "text": replacement[start:start + chunk_size]}, ensure_ascii=False) + "\n"
            await asyncio.sleep(0)
        if await request.is_disconnected():
            return
        revision = await persist_prepared_edit(db, project_id, unit_id, user.id, command, prepared)
        yield json.dumps({"type": "candidate", "revision": revision.model_dump(mode="json")}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post(
    "/projects/{project_id}/manuscript/ai-edits/{revision_id}/{action}",
    response_model=ManuscriptEditRevisionView,
)
async def resolve_manuscript_ai_edit(
    project_id: int, revision_id: int, action: str, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await resolve_edit(db, project_id, revision_id, user.id, action)


@app.post(
    "/projects/{project_id}/story-bible/character-introductions",
    response_model=StoryBibleChangeView,
)
async def preview_character_introduction(
    project_id: int, command: CreateCharacterIntroduction, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await create_character_introduction(db, project_id, user.id, command)


@app.post("/projects/{project_id}/story-bible/relationship-changes", response_model=StoryBibleChangeView)
async def preview_relationship_change(
    project_id: int, command: CreateRelationshipChange, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await create_relationship_change(db, project_id, user.id, command)


@app.post("/projects/{project_id}/story-bible/world-rule-changes", response_model=StoryBibleChangeView)
async def preview_world_rule_change(
    project_id: int, command: CreateWorldRuleChange, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await create_world_rule_change(db, project_id, user.id, command)


@app.post("/projects/{project_id}/story-bible/foreshadow-plan-changes", response_model=StoryBibleChangeView)
async def preview_foreshadow_plan_change(
    project_id: int, command: CreateForeshadowPlanChange, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await create_foreshadow_plan_change(db, project_id, user.id, command)


@app.get("/projects/{project_id}/story-bible/changes", response_model=list[StoryBibleChangeView])
async def get_story_bible_changes(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_changes(db, project_id, user.id)


@app.post(
    "/projects/{project_id}/story-bible/changes/{change_id}/{action}",
    response_model=StoryBibleChangeView,
)
async def resolve_story_bible_change(
    project_id: int, change_id: int, action: str, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await resolve_change(db, project_id, change_id, user.id, action)


@app.get("/projects/{project_id}/cascade-revisions", response_model=list[CascadeRevisionView])
async def get_cascade_revisions(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_cascade_revisions(db, project_id, user.id)


@app.post(
    "/projects/{project_id}/cascade-revisions/{revision_id}/{action}",
    response_model=CascadeRevisionView,
)
async def resolve_cascade(
    project_id: int, revision_id: int, action: str, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await resolve_cascade_revision(db, project_id, revision_id, user.id, action)


@app.get(
    "/projects/{project_id}/manuscript-impact-candidates",
    response_model=list[ManuscriptImpactCandidateView],
)
async def get_manuscript_impact_candidates(
    project_id: int, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await list_impact_candidates(db, project_id, user.id)


@app.post(
    "/projects/{project_id}/manuscript-impact-candidates/{candidate_id}/{action}",
    response_model=ManuscriptImpactCandidateView,
)
async def resolve_manuscript_impact(
    project_id: int, candidate_id: int, action: str, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await resolve_impact_candidate(db, project_id, candidate_id, user.id, action)


@app.get("/projects/{project_id}/plan", response_model=ProjectPlanView)
async def get_project_plan(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_plan(db, project_id, user.id)


@app.post("/projects/{project_id}/plan/impact", response_model=ProjectPlanImpactView)
async def preview_project_plan_change(
    project_id: int, command: ProjectPlanChange, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await preview_plan_change(db, project_id, user.id, command)


@app.patch("/projects/{project_id}/plan", response_model=ProjectPlanView)
async def patch_project_plan(
    project_id: int, command: ProjectPlanChange, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await apply_plan_change(db, project_id, user.id, command)


@app.get("/projects/{project_id}/story-map", response_model=StoryMapView)
async def read_story_map(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_story_map(db, project_id, user.id)


@app.patch("/projects/{project_id}/story-map/units/{unit_id}", response_model=StoryMapUnitView)
async def patch_story_map_unit(
    project_id: int, unit_id: int, command: StoryMapUnitUpdate, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await update_story_map_unit(db, project_id, user.id, unit_id, command)


@app.post("/projects/{project_id}/story-map/groups/{group_id}/units", response_model=StoryMapUnitView)
async def create_story_map_unit(
    project_id: int, group_id: int, command: CreateStoryMapUnit, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await add_story_map_unit(db, project_id, user.id, group_id, command)


@app.put("/projects/{project_id}/story-map/groups/{group_id}/order", response_model=StoryMapView)
async def reorder_story_map_group(
    project_id: int, group_id: int, command: ReorderStoryMapUnits, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await reorder_story_map_units(db, project_id, user.id, group_id, command)


@app.post("/projects/{project_id}/tasks/{task_id}/run", response_model=TaskView)
async def execute_task(project_id: int, task_id: int, db: AsyncSession = Depends(session)):
    return await run_task(db, project_id, task_id)


@app.post("/projects/{project_id}/story-cores/{candidate_id}/adopt", response_model=ProjectView)
async def adopt_story_core(project_id: int, candidate_id: int, db: AsyncSession = Depends(session)):
    return await adopt_candidate(db, project_id, candidate_id)


@app.get("/projects/{project_id}/continuity", response_model=ContinuityView)
async def get_continuity(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await continuity_view(db, project_id, user.id)


@app.get("/projects/{project_id}/continuity/next-context", response_model=ContextPreviewView)
async def get_next_context_preview(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await preview_next_context(db, project_id, user.id)


@app.post("/projects/{project_id}/entities", response_model=NarrativeEntityView)
async def add_narrative_entity(project_id: int, command: CreateNarrativeEntity, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await create_entity(db, project_id, user.id, command)


@app.post("/projects/{project_id}/relationships", response_model=NarrativeRelationshipView)
async def add_narrative_relationship(project_id: int, command: NarrativeRelationshipCommand, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await create_relationship(db, project_id, user.id, command)


@app.get("/projects/{project_id}/relationships", response_model=list[NarrativeRelationshipView])
async def get_narrative_relationships(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_relationships(db, project_id, user.id)


@app.post("/projects/{project_id}/foreshadows", response_model=ForeshadowView)
async def add_foreshadow(project_id: int, command: CreateForeshadow, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await create_foreshadow(db, project_id, user.id, command)


@app.get("/projects/{project_id}/foreshadows", response_model=list[ForeshadowView])
async def get_foreshadows(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_foreshadows(db, project_id, user.id)


@app.post("/projects/{project_id}/foreshadows/{foreshadow_id}/transition", response_model=ForeshadowView)
async def change_foreshadow(project_id: int, foreshadow_id: int, command: ForeshadowTransition, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await transition_foreshadow(db, project_id, user.id, foreshadow_id, command)


@app.post("/projects/{project_id}/directives", response_model=DirectiveView)
async def add_directive(project_id: int, command: CreateDirective, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await create_directive(db, project_id, user.id, command)


@app.get("/projects/{project_id}/directives", response_model=list[DirectiveView])
async def get_directives(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await list_directives(db, project_id, user.id)


@app.post("/projects/{project_id}/manuscript/opening", response_model=ManuscriptUnitView)
async def create_opening(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await draft_opening(db, project_id, user.id)


@app.post("/projects/{project_id}/manuscript/next", response_model=ManuscriptUnitView)
async def create_next_unit(
    project_id: int, story_map_unit_id: int | None = None, db: AsyncSession = Depends(session),
):
    user = await demo_user(db)
    return await draft_opening(db, project_id, user.id, story_map_unit_id)


@app.get("/projects/{project_id}/manuscript/opening", response_model=ManuscriptUnitView | None)
async def read_opening(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_opening(db, project_id, user.id)


@app.get("/projects/{project_id}/manuscript/latest", response_model=ManuscriptUnitView | None)
async def read_latest_unit(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_latest_unit(db, project_id, user.id)


@app.get("/projects/{project_id}/manuscript/units/{manuscript_unit_id}", response_model=ManuscriptUnitView)
async def read_manuscript_unit(project_id: int, manuscript_unit_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_manuscript_unit(db, project_id, manuscript_unit_id, user.id)


@app.post("/projects/{project_id}/manuscript/{candidate_id}/adopt", response_model=ManuscriptUnitView)
async def adopt_opening(project_id: int, candidate_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await adopt_manuscript(db, project_id, candidate_id, user.id)


@app.post("/projects/{project_id}/manuscript/{candidate_id}/revise", response_model=ManuscriptUnitView)
async def revise_candidate(project_id: int, candidate_id: int, command: ReviseRequest, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await revise_manuscript(db, project_id, candidate_id, command.feedback, user.id)





@app.post("/projects/{project_id}/revisions", response_model=RevisionView)
async def create_revision(project_id: int, command: CreateRevision, db: AsyncSession = Depends(session)):
    return await create(db, project_id, command)


@app.post("/projects/{project_id}/revisions/{revision_id}/{action}", response_model=RevisionView)
async def resolve_revision(project_id: int, revision_id: int, action: str, db: AsyncSession = Depends(session)):
    return await resolve(db, project_id, revision_id, action)


@app.get("/projects/{project_id}/living-asset-candidates", response_model=list[LivingAssetCandidateView])
async def read_living_asset_candidates(project_id: int, db: AsyncSession = Depends(session)):
    return await list_candidates(db, project_id)


@app.post("/projects/{project_id}/living-asset-candidates/{candidate_id}/{action}", response_model=LivingAssetCandidateView)
async def decide_living_asset_candidate(project_id: int, candidate_id: int, action: str, db: AsyncSession = Depends(session)):
    return await resolve_candidate(db, project_id, candidate_id, action)


@app.get("/structures")
async def list_structures():
    return structure_labels()


@app.get("/mediums")
async def list_mediums():
    return profile_labels()


# ═══ Story Architecture ═══
# ═══ Story Architecture ═══
from pydantic import BaseModel

class ReviseRequest(BaseModel):
    feedback: str

class ArchitectureResponse(BaseModel):
    status: str = ""
    thesis: str = ""
    approach: str = ""
    agent_session: dict | list = {}
    arcs: list[dict] = []

class ArcUpdateRequest(BaseModel):
    title: str | None = None
    episode_start: int | None = None
    episode_end: int | None = None
    core_conflict: str | None = None
    emotional_landing: str | None = None
    protag_state: str | None = None
    antag_state: str | None = None
    must_have_events: list[str] | None = None
    foreshadow_actions: list[str] | None = None
    status: str | None = None


@app.get("/projects/{project_id}/architecture", response_model=ArchitectureResponse)
async def read_architecture(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await get_architecture(db, project_id, user.id)


@app.post("/projects/{project_id}/architecture/plan", response_model=ArchitectureResponse)
async def generate_architecture(project_id: int, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await plan_architecture(db, project_id, user.id)


@app.patch("/projects/{project_id}/architecture/arcs/{arc_id}")
async def patch_arc(project_id: int, arc_id: int, command: ArcUpdateRequest, db: AsyncSession = Depends(session)):
    user = await demo_user(db)
    return await update_arc(db, project_id, arc_id, user.id, command.model_dump(exclude_none=True))
