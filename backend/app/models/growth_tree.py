"""Growth Tree — the DAG that models how each artefact was grown.

Nodes represent artefacts (idea / structure / outline / episode / scene / asset)
and edges represent lineage relationships (``derived_from`` / ``revised_from``
/ ``references``). See ADR-0001 for why this exists.

Design choices:
- Two flat tables (nodes + edges) rather than a graph DB — SQLite can walk
  a few hundred nodes with a Python BFS trivially, and we never leave SQLite
  in tests.
- ``ref_id`` links a node back to its concrete row (episode.id, character.id, …).
  ``node_type`` doubles as the type of the referenced entity.
- ``metadata`` (JSON string) holds UI-friendly summaries (e.g. an outline's
  one-line pitch) so tree views don't have to join across a dozen tables.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base

NODE_TYPES = ("idea", "structure", "outline", "episode", "scene", "asset")
EDGE_TYPES = ("derived_from", "revised_from", "references")


class GrowthNode(Base):
    __tablename__ = "growth_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    node_type = Column(String(20), nullable=False)  # see NODE_TYPES
    ref_id = Column(Integer, nullable=True)  # nullable for orphan/placeholder nodes
    label = Column(String(200), default="")
    metadata_json = Column("metadata", Text, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GrowthEdge(Base):
    __tablename__ = "growth_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    from_node_id = Column(Integer, ForeignKey("growth_nodes.id"), nullable=False)
    to_node_id = Column(Integer, ForeignKey("growth_nodes.id"), nullable=False)
    edge_type = Column(String(20), nullable=False, default="derived_from")  # see EDGE_TYPES
    created_at = Column(DateTime(timezone=True), server_default=func.now())
