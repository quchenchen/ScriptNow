"""Growth Tree API — read + Cascade preview.

All endpoints project-scoped; ownership verified via ``OwnedProject``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import OwnedProject
from app.services import growth_tree_service as tree_svc

router = APIRouter()


@router.get("/{project_id}/tree")
async def get_project_tree(project: OwnedProject):
    """Full ``{nodes, edges}`` snapshot for the project."""
    return await tree_svc.get_tree(project["id"])


@router.get("/{project_id}/tree/lineage/{node_id}")
async def get_lineage(project: OwnedProject, node_id: int):
    """Ancestors of a node, root → parent order."""
    node = await tree_svc._load_node(node_id)
    if not node or node.project_id != project["id"]:
        raise HTTPException(404, "节点不存在")
    ancestors = await tree_svc.lineage(node_id)
    return {"node_id": node_id, "ancestors": [n.__dict__ for n in ancestors]}


@router.get("/{project_id}/tree/descendants/{node_id}")
async def get_descendants(project: OwnedProject, node_id: int):
    """Descendants of a node (transitively), BFS order."""
    node = await tree_svc._load_node(node_id)
    if not node or node.project_id != project["id"]:
        raise HTTPException(404, "节点不存在")
    descs = await tree_svc.descendants(node_id)
    return {"node_id": node_id, "descendants": [n.__dict__ for n in descs]}


@router.post("/{project_id}/tree/mark-dirty")
async def mark_dirty(project: OwnedProject, data: dict):
    """Preview downstream episode/scene nodes affected by a source change.

    Body: ``{"source_node_id": int}``.

    We don't persist a dirty flag yet — issue #07 introduces cascade markers.
    """
    source_id = data.get("source_node_id")
    if not isinstance(source_id, int):
        raise HTTPException(400, "source_node_id 必需")
    node = await tree_svc._load_node(source_id)
    if not node or node.project_id != project["id"]:
        raise HTTPException(404, "节点不存在")
    affected = await tree_svc.mark_dirty(source_id)
    return {
        "source_node_id": source_id,
        "affected_nodes": [n.__dict__ for n in affected],
    }


@router.post("/{project_id}/tree/backfill")
async def backfill(project: OwnedProject):
    """Rebuild the tree from existing project data. Idempotent."""
    summary = await tree_svc.backfill_project(project["id"])
    return summary
