import hashlib
from collections.abc import Callable

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import DeliveryStatus, ProjectEventModel, ProjectModel
from scriptnow.platform.translation_contracts import (
    TranslationError,
    TranslationService,
    TranslationUnit,
)
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import (
    RevisionStatus,
    ScriptDocumentRevisionModel,
    ScriptExportManifestModel,
)
from scriptnow.script.export import ScriptExportScene, render_script_docx
from scriptnow.script.project import ScriptPlanModel, ScriptStoryMapModel


class ScriptDeliveryError(RuntimeError):
    pass


class ScriptExportService:
    def __init__(
        self,
        database: Database,
        renderer: Callable[..., bytes] = render_script_docx,
        translator: TranslationService | None = None,
    ) -> None:
        self.database = database
        self.renderer = renderer
        self.translator = translator

    async def options(self, *, tenant_id: str, project_id: str) -> dict[str, object]:
        async with self.database.session() as session:
            project = await _project(session, tenant_id, project_id)
            story_map = (
                await session.scalars(
                    select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project.id)
                )
            ).one()
            adopted = set(
                await session.scalars(
                    select(ScriptDocumentRevisionModel.scene_id).where(
                        ScriptDocumentRevisionModel.project_id == project.id,
                        ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                    )
                )
            )
            episodes = []
            for episode in story_map.episodes:
                scenes = [
                    {
                        "id": str(scene["id"]),
                        "title": str(scene["title"]),
                        "status": "done" if str(scene["id"]) in adopted else "empty",
                        "selectable": str(scene["id"]) in adopted,
                    }
                    for scene in episode.get("scenes", [])
                ]
                selected = sum(bool(item["selectable"]) for item in scenes)
                episodes.append(
                    {
                        "id": str(episode["id"]),
                        "title": str(episode["title"]),
                        "selection": "all"
                        if scenes and selected == len(scenes)
                        else "partial"
                        if selected
                        else "none",
                        "scenes": scenes,
                    }
                )
            return {
                "project_id": project.id,
                "creative_language": str(project.direction.get("language") or ""),
                "episodes": episodes,
            }

    async def export(
        self,
        *,
        tenant_id: str,
        project_id: str,
        scene_ids: tuple[str, ...],
        form: str,
        idempotency_key: str,
        translation_mode: str = "none",
        target_language: str | None = None,
    ) -> ScriptExportManifestModel:
        if not scene_ids or len(scene_ids) != len(set(scene_ids)):
            raise ScriptDeliveryError("export scope must contain unique scenes")
        if form not in {"clean", "working"}:
            raise ScriptDeliveryError("unsupported Script export form")
        if translation_mode not in {"none", "faithful"}:
            raise ScriptDeliveryError("归化翻译敬请期待，当前仅支持常规翻译")
        if translation_mode == "faithful" and not target_language:
            raise ScriptDeliveryError("常规翻译需要选择目标语言")
        async with self.database.session() as session:
            project = await _project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(ScriptExportManifestModel).where(
                        ScriptExportManifestModel.project_id == project_id,
                        ScriptExportManifestModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing and existing.status == DeliveryStatus.SUCCEEDED:
                return existing
            plan = (
                await session.scalars(
                    select(ScriptPlanModel).where(ScriptPlanModel.project_id == project_id)
                )
            ).one()
            story_map = (
                await session.scalars(
                    select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project_id)
                )
            ).one()
            revisions = list(
                await session.scalars(
                    select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.scene_id.in_(scene_ids),
                        ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                    )
                )
            )
            by_scene = {item.scene_id: item for item in revisions}
            if set(scene_ids) != set(by_scene):
                raise ScriptDeliveryError("only completed scenes can be exported")
            scenes = _ordered_scenes(story_map.episodes, scene_ids, by_scene)
            if translation_mode == "faithful":
                if self.translator is None:
                    raise ScriptDeliveryError("translation service is unavailable")
                try:
                    translated = await self.translator.translate(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_language=str(project.direction.get("language") or ""),
                        target_language=str(target_language),
                        units=tuple(
                            TranslationUnit(
                                titles={
                                    "episode_title": scene.episode_title,
                                    "scene_title": scene.scene_title,
                                },
                                blocks=tuple(block.model_dump(mode="json") for block in scene.blocks),
                            )
                            for scene in scenes
                        ),
                        idempotency_key=idempotency_key,
                    )
                except TranslationError as error:
                    raise ScriptDeliveryError(str(error)) from error
                scenes = [
                    ScriptExportScene(
                        episode_title=unit.titles["episode_title"],
                        scene_title=unit.titles["scene_title"],
                        blocks=tuple(ScriptBlock.model_validate(block) for block in unit.blocks),
                    )
                    for unit in translated
                ]
            script_format = str(plan.direction.get("script_format") or "")
            if script_format not in {"chinese", "hollywood"}:
                raise ScriptDeliveryError("project Script format is invalid")
            manifest = existing or ScriptExportManifestModel(
                project_id=project_id,
                idempotency_key=idempotency_key,
                scope=list(scene_ids),
                script_format=script_format,
                form=form,
                status=DeliveryStatus.PENDING,
            )
            if existing is None:
                session.add(manifest)
            manifest.attempts = (manifest.attempts or 0) + 1
            manifest.error = None
            try:
                artifact = self.renderer(
                    project_name=project.name,
                    script_format=script_format,
                    scenes=tuple(scenes),
                )
            except Exception as error:
                manifest.status = DeliveryStatus.FAILED
                manifest.error = str(error)[:500]
                await session.flush()
                return manifest
            manifest.artifact = artifact
            manifest.artifact_sha256 = hashlib.sha256(artifact).hexdigest()
            manifest.byte_size = len(artifact)
            manifest.status = DeliveryStatus.SUCCEEDED
            await _event(session, tenant_id, project_id, manifest)
            await session.flush()
            return manifest


async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if project is None or project.tenant_id != tenant_id or project.medium != "script":
        raise ScriptDeliveryError("Script project is outside tenant scope")
    return project


def _ordered_scenes(episodes, scope, by_scene) -> list[ScriptExportScene]:
    selected = set(scope)
    result = []
    for episode in episodes:
        for scene in episode.get("scenes", []):
            scene_id = str(scene["id"])
            if scene_id in selected:
                revision = by_scene[scene_id]
                result.append(
                    ScriptExportScene(
                        episode_title=str(episode["title"]),
                        scene_title=str(scene["title"]),
                        blocks=tuple(ScriptBlock.model_validate(item) for item in revision.blocks),
                    )
                )
    if len(result) != len(selected):
        raise ScriptDeliveryError("export scope contains a scene outside StoryMap")
    return result


async def _event(session, tenant_id: str, project_id: str, manifest) -> None:
    stream_key = f"project:{project_id}"
    sequence = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(ProjectEventModel.sequence), 0)).where(
                    ProjectEventModel.stream_key == stream_key
                )
            )
            or 0
        )
        + 1
    )
    session.add(
        ProjectEventModel(
            tenant_id=tenant_id,
            project_id=project_id,
            stream_key=stream_key,
            sequence=sequence,
            event_key=f"script:export:{manifest.id}",
            event_type="node",
            actor={"type": "user", "id": tenant_id},
            aggregate={"type": "script_export", "id": manifest.id},
            correlation_id=manifest.id,
            idempotency_key=manifest.idempotency_key,
            payload={"action": "script.exported", "scope": manifest.scope, "form": manifest.form},
        )
    )
