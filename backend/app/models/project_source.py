"""ProjectSource + SourceChunk — uploaded reference documents for adaption/rewrite.

See ADR-0004 (progressive-disclosure memory) and issue #14. A ``ProjectSource``
is one uploaded file (e.g. ``《X》.docx``); a ``SourceChunk`` is a slice of that
file's text with an optional embedding vector used for RAG-style retrieval.

Design choices:
- Embeddings stored as raw ``numpy.float32`` bytes in a BLOB column —
  zero-dep, retrieval is a Python cosine loop; fast enough for tens of
  thousands of chunks. Move to sqlite-vec if we outgrow this.
- ``status`` on ``ProjectSource`` runs pending → parsing → indexing → done
  (or failed); the upload API returns immediately after ``pending`` and the
  UI polls for progress.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.sql import func

from .base import Base


class ProjectSource(Base):
    __tablename__ = "project_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime = Column(String(80), default="")
    file_path = Column(String(500), default="")  # relative to backend/data/uploads
    size_bytes = Column(Integer, default=0)
    total_chars = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    summary = Column(Text, default="")
    status = Column(String(20), default="pending")  # pending|parsing|indexing|done|failed
    error = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("project_sources.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)  # 0-based, dense
    content = Column(Text, nullable=False)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    embedding = Column(LargeBinary, nullable=True)  # np.float32 bytes, or NULL if no embedding
    created_at = Column(DateTime(timezone=True), server_default=func.now())
