from types import SimpleNamespace

import pytest
from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    NarrativeTextUnitModel,
    ProjectMedium,
    ProjectModel,
    TenantModel,
    WorkspaceFileModel,
    WorkspaceFileStatus,
)
from scriptnow.platform.narrative_graph import (
    NarrativeEdgeInput,
    NarrativeGraphService,
    NarrativeNodeInput,
    NarrativeSummaryInput,
    segment_novel_text,
)
from scriptnow.platform.narrative_graph_api import (
    _readable_edge_rows,
    _readable_node_rows,
)
from scriptnow.platform.narrative_graph_extractor import (
    NarrativeGraphExtractionError,
    NarrativeGraphExtractor,
)
from scriptnow.platform.narrative_graph_schema import (
    NarrativeNodeType,
    NarrativeRelationType,
    canonical_node_type,
    canonical_relation_type,
    compatible_node_type,
    compatible_relation_type,
)


@pytest.fixture
async def narrative_database():
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    yield database
    await database.dispose()


def test_semantic_segmentation_preserves_chapter_and_paragraph_boundaries() -> None:
    text = "\n".join(
        [
            "Chapter 1 — The Door",
            "Alpha " * 150,
            "Beta " * 150,
            "Chapter 2: The Return",
            "Gamma " * 150,
        ]
    )

    units = segment_novel_text(text, target_characters=700)

    assert [unit.chapter_key for unit in units] == ["chapter-1", "chapter-1", "chapter-2"]
    assert units[0].content.endswith("Alpha ".strip())
    assert units[1].content.startswith("Beta")
    assert all("Chapter 2" not in unit.content for unit in units)


def test_graph_extraction_contract_accepts_grounded_json_and_rejects_unknown_evidence() -> None:
    text = """{
      "chapter_title": "The Moon Ball",
      "chapter_summary": "Sera is rejected and leaves with a new question.",
      "nodes": [
        {"key":"character:sera","type":"character","name":"Sera","aliases":[],
         "description":"The protagonist chooses to leave.","evidence_ordinals":[2]},
        {"key":"event:rejection","type":"event","name":"The rejection","aliases":[],
         "description":"The bond is rejected in public.","evidence_ordinals":[2]}
      ],
      "edges": [
        {"key":"sera-in-rejection","type":"participates_in","source":"character:sera",
         "target":"event:rejection","description":"Sera experiences the rejection.",
         "evidence_ordinals":[2],"confidence":96,"inference":false}
      ]
    }"""
    payload = NarrativeGraphExtractor.parse(text, allowed_ordinals={2})
    assert payload.edges[0].source == "character:sera"
    assert payload.edges[0].type is NarrativeRelationType.AFFILIATION
    wrapped = NarrativeGraphExtractor.parse(
        f'[["graph contract"], {text}]', allowed_ordinals={2}
    )
    assert wrapped.chapter_title == "The Moon Ball"

    with pytest.raises(NarrativeGraphExtractionError, match="unknown source unit"):
        NarrativeGraphExtractor.parse(text, allowed_ordinals={3})


def test_graph_taxonomy_collapses_legacy_aliases_and_rejects_new_categories() -> None:
    assert canonical_node_type("faction") is NarrativeNodeType.ORGANIZATION
    assert canonical_node_type("world_rule") is NarrativeNodeType.CONCEPT
    assert canonical_node_type("motif") is NarrativeNodeType.CONCEPT
    assert canonical_node_type("promise") is NarrativeNodeType.STORY_THREAD
    assert canonical_relation_type("discovers") is NarrativeRelationType.CAUSAL
    assert canonical_relation_type("participates_in") is NarrativeRelationType.AFFILIATION

    with pytest.raises(ValueError, match="unsupported narrative node type"):
        canonical_node_type("interesting_new_type")
    with pytest.raises(ValueError, match="unsupported narrative relation type"):
        canonical_relation_type("some_relation")


def test_graph_read_compatibility_contains_unknown_historical_values() -> None:
    assert compatible_node_type("unknown_legacy_node") is NarrativeNodeType.CONCEPT
    assert compatible_relation_type("unknown_legacy_edge") is NarrativeRelationType.AFFILIATION


def test_graph_read_skips_one_damaged_row_without_losing_valid_graph() -> None:
    unit = SimpleNamespace(
        chapter_title="Chapter 1",
        chapter_key="chapter-1",
        contextual_header="Chapter 1 · passage 1",
    )
    valid_node = SimpleNamespace(
        id="node-1",
        node_type="person",
        name="Sera",
        description="Protagonist",
        evidence_unit_ids=["unit-1"],
    )
    unknown_node = SimpleNamespace(
        id="node-2",
        node_type="legacy_archetype",
        name="The bond",
        description="A historical unknown type",
        evidence_unit_ids=[],
    )
    damaged_node = SimpleNamespace(id="broken")

    nodes = _readable_node_rows(
        [valid_node, damaged_node, unknown_node], {"unit-1": unit}
    )
    assert [node["id"] for node in nodes] == ["node-1", "node-2"]
    assert [node["type"] for node in nodes] == ["character", "concept"]

    valid_edge = SimpleNamespace(
        id="edge-1",
        edge_type="protects",
        source_node_id="node-1",
        target_node_id="node-2",
        description="Sera protects the bond.",
        inference=False,
    )
    orphan_edge = SimpleNamespace(
        id="edge-orphan",
        edge_type="causal",
        source_node_id="node-1",
        target_node_id="missing",
        description="Broken endpoint.",
        inference=False,
    )
    damaged_edge = SimpleNamespace(id="edge-broken")
    edges = _readable_edge_rows(
        [valid_edge, damaged_edge, orphan_edge], {"node-1", "node-2"}
    )
    assert len(edges) == 1
    assert edges[0]["type"] == "emotional"


@pytest.mark.asyncio
async def test_index_is_versioned_idempotent_and_hybrid_retrievable(
    narrative_database,
) -> None:
    database = narrative_database
    async with database.session() as session:
        tenant = TenantModel(name="Narrative tenant")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="Moonbound",
            medium=ProjectMedium.NOVEL,
        )
        session.add(project)
        await session.flush()
        source = WorkspaceFileModel(
            tenant_id=tenant.id,
            project_id=project.id,
            original_name="novel.docx",
            storage_name="novel.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            byte_size=100,
            sha256="a" * 64,
            status=WorkspaceFileStatus.READY,
        )
        session.add(source)
        await session.flush()
        tenant_id, project_id, source_id = tenant.id, project.id, source.id

    text = "\n".join(
        [
            "Chapter 1 — Rejection",
            "Sera rejects the forced bond and leaves the valley.",
            "Chapter 2 — Evidence",
            "The silver leaf opens the sealed archive and reveals the council record.",
        ]
    )
    service = NarrativeGraphService(database)
    first = await service.build_index(
        tenant_id=tenant_id,
        project_id=project_id,
        source_file_id=source_id,
        parsed_text=text,
        target_characters=700,
    )
    repeated = await service.build_index(
        tenant_id=tenant_id,
        project_id=project_id,
        source_file_id=source_id,
        parsed_text=text,
        target_characters=700,
    )
    assert repeated.id == first.id

    async with database.session() as session:
        units = list(
            (
                await session.scalars(
                    select(NarrativeTextUnitModel)
                    .where(NarrativeTextUnitModel.index_id == first.id)
                    .order_by(NarrativeTextUnitModel.ordinal)
                )
            ).all()
        )
    sera = await service.record_node(
        tenant_id=tenant_id,
        index_id=first.id,
        item=NarrativeNodeInput(
            node_key="character:sera",
            node_type="character",
            name="Sera",
            aliases=("Silver heir",),
            description="The protagonist.",
            attributes={},
            evidence_unit_ids=(units[0].id, units[1].id),
        ),
    )
    archive = await service.record_node(
        tenant_id=tenant_id,
        index_id=first.id,
        item=NarrativeNodeInput(
            node_key="location:archive",
            node_type="location",
            name="sealed archive",
            aliases=(),
            description="A protected record store.",
            attributes={},
            evidence_unit_ids=(units[1].id,),
        ),
    )
    edge = await service.record_edge(
        tenant_id=tenant_id,
        index_id=first.id,
        item=NarrativeEdgeInput(
            edge_key="sera-opens-archive",
            edge_type="discovers",
            source_node_key="character:sera",
            target_node_key="location:archive",
            description="Sera reaches evidence in the archive.",
            evidence_unit_ids=(units[1].id,),
            confidence=90,
        ),
    )
    summary = await service.record_summary(
        tenant_id=tenant_id,
        index_id=first.id,
        item=NarrativeSummaryInput(
            summary_key="chapter-2",
            level="chapter",
            title="Evidence",
            content="The archive exposes the hidden record.",
            child_unit_ids=(units[1].id,),
            evidence_node_ids=(sera.id, archive.id),
        ),
    )
    assert edge.evidence_unit_ids == [units[1].id]
    assert summary.child_unit_ids == [units[1].id]

    hits = await service.retrieve(
        tenant_id=tenant_id,
        index_id=first.id,
        query="Sera sealed archive",
        semantic_scores={units[1].id: 0.9},
    )

    assert [hit.ordinal for hit in hits[:2]] == [1, 0]
    assert "semantic" in hits[0].reasons
    assert "graph" in hits[0].reasons
