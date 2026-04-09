"""007 indexes: B-tree and vector indexes

Revision ID: 007
Revises: 006
Create Date: 2026-04-09
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Patients
    op.create_index("ix_patients_mrn", "patients", ["mrn"])

    # Encounters
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"])
    op.create_index("ix_encounters_provider_id", "encounters", ["provider_id"])
    op.create_index("ix_encounters_encounter_time", "encounters", ["encounter_time"])

    # Lab results
    op.create_index("ix_lab_results_report_id", "lab_results", ["report_id"])

    # ICD / CPT catalog
    op.create_index("ix_icd_catalog_code", "icd_catalog", ["code"])
    op.create_index("ix_icd_catalog_chapter", "icd_catalog", ["chapter"])
    op.create_index("ix_cpt_catalog_code", "cpt_catalog", ["code"])

    # Knowledge chunks — B-tree for patient_id filter, GIN for JSONB metadata
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_patient_id", "knowledge_chunks", ["patient_id"])
    op.create_index("ix_knowledge_chunks_content_hash", "knowledge_chunks", ["content_hash"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_metadata ON knowledge_chunks USING GIN (metadata_json)"
    )

    # Vector index (IVFFlat for cosine similarity)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding "
        "ON knowledge_chunks USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = 100)"
    )

    # Ops
    op.create_index("ix_llm_calls_request_id", "llm_calls", ["request_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_patient_id", "audit_events", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_patient_id", "audit_events")
    op.drop_index("ix_audit_events_event_type", "audit_events")
    op.drop_index("ix_llm_calls_request_id", "llm_calls")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_metadata")
    op.drop_index("ix_knowledge_chunks_content_hash", "knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_patient_id", "knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", "knowledge_chunks")
    op.drop_index("ix_cpt_catalog_code", "cpt_catalog")
    op.drop_index("ix_icd_catalog_chapter", "icd_catalog")
    op.drop_index("ix_icd_catalog_code", "icd_catalog")
    op.drop_index("ix_lab_results_report_id", "lab_results")
    op.drop_index("ix_encounters_encounter_time", "encounters")
    op.drop_index("ix_encounters_provider_id", "encounters")
    op.drop_index("ix_encounters_patient_id", "encounters")
    op.drop_index("ix_patients_mrn", "patients")
