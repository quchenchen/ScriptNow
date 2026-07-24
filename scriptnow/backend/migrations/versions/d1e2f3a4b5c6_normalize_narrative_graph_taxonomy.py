"""normalize historical narrative graph taxonomy

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Collapse legacy node labels into the deliberately small V7 taxonomy.
    op.execute(
        """
        UPDATE narrative_nodes
        SET node_type = CASE
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('character', 'person') THEN 'character'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('event', 'plot_event') THEN 'event'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('organization', 'organisation', 'faction', 'group') THEN 'organization'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('location', 'place') THEN 'location'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('object', 'artifact', 'prop') THEN 'object'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('relationship', 'relation') THEN 'relationship'
          WHEN lower(replace(replace(trim(node_type), ' ', '_'), '-', '_'))
            IN ('story_thread', 'foreshadow', 'setup', 'promise', 'mystery') THEN 'story_thread'
          ELSE 'concept'
        END
        """
    )
    # Match the same precedence as canonical_relation_type. Unknown historical
    # values become the generic affiliation relation instead of breaking reads.
    op.execute(
        """
        UPDATE narrative_edges
        SET edge_type = CASE
          WHEN lower(trim(edge_type)) IN
            ('causal', 'emotional', 'conflict', 'foreshadowing', 'constraint', 'affiliation')
            THEN lower(trim(edge_type))
          WHEN lower(edge_type) LIKE '%conflict%' OR lower(edge_type) LIKE '%oppose%'
            OR lower(edge_type) LIKE '%threat%' OR lower(edge_type) LIKE '%reject%'
            OR lower(edge_type) LIKE '%attack%' OR lower(edge_type) LIKE '%kill%'
            OR lower(edge_type) LIKE '%betray%' OR lower(edge_type) LIKE '%rival%'
            THEN 'conflict'
          WHEN lower(edge_type) LIKE '%cause%' OR lower(edge_type) LIKE '%lead%'
            OR lower(edge_type) LIKE '%trigger%' OR lower(edge_type) LIKE '%result%'
            OR lower(edge_type) LIKE '%change%' OR lower(edge_type) LIKE '%reveal%'
            OR lower(edge_type) LIKE '%discover%' OR lower(edge_type) LIKE '%find%'
            OR lower(edge_type) LIKE '%learn%' OR lower(edge_type) LIKE '%enable%'
            OR lower(edge_type) LIKE '%prevent%' OR lower(edge_type) LIKE '%progress%'
            THEN 'causal'
          WHEN lower(edge_type) LIKE '%bond%' OR lower(edge_type) LIKE '%love%'
            OR lower(edge_type) LIKE '%trust%' OR lower(edge_type) LIKE '%protect%'
            OR lower(edge_type) LIKE '%family%' OR lower(edge_type) LIKE '%kin%'
            OR lower(edge_type) LIKE '%emotion%' THEN 'emotional'
          WHEN lower(edge_type) LIKE '%foreshadow%' OR lower(edge_type) LIKE '%setup%'
            OR lower(edge_type) LIKE '%payoff%' OR lower(edge_type) LIKE '%promise%'
            OR lower(edge_type) LIKE '%echo%' OR lower(edge_type) LIKE '%motif%'
            THEN 'foreshadowing'
          WHEN lower(edge_type) LIKE '%rule%' OR lower(edge_type) LIKE '%govern%'
            OR lower(edge_type) LIKE '%constrain%' OR lower(edge_type) LIKE '%require%'
            OR lower(edge_type) LIKE '%forbid%' OR lower(edge_type) LIKE '%permit%'
            OR lower(edge_type) LIKE '%limit%' THEN 'constraint'
          ELSE 'affiliation'
        END
        """
    )


def downgrade() -> None:
    # Historical spellings cannot be reconstructed after canonicalization.
    pass
