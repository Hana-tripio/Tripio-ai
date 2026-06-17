from pathlib import Path


def test_initial_migration_defines_tripio_ai_tables_and_pgvector() -> None:
    migration = Path("alembic/versions/20260616_0001_initial_ai_schema.py")

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    for table_name in [
        "regions",
        "places",
        "place_sources",
        "events",
        "region_metrics",
        "rag_documents",
        "ingestion_runs",
    ]:
        assert "op.create_table(" in source
        assert f'"{table_name}"' in source

    assert "embedding" in source
    assert "Vector(1536)" in source
    assert "idx_places_region_category" in source
    assert "uq_place_sources_source_external_id" in source


def test_database_settings_include_postgres_url() -> None:
    config = Path("app/core/config.py").read_text(encoding="utf-8")

    assert "database_url" in config
    assert "postgresql+psycopg" in config


def test_place_sync_fields_are_defined_in_models() -> None:
    models = Path("app/db/models.py").read_text(encoding="utf-8")

    for field_name in [
        "sync_status",
        "canonical_place_key",
        "review_reason",
        "backend_place_id",
        "last_synced_at",
        "sync_error_message",
    ]:
        assert field_name in models


def test_place_sync_fields_migration_exists() -> None:
    migration = Path("alembic/versions/20260617_0002_add_place_sync_fields.py")

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")

    for field_name in [
        "sync_status",
        "canonical_place_key",
        "review_reason",
        "backend_place_id",
        "last_synced_at",
        "sync_error_message",
    ]:
        assert field_name in source

    assert "idx_places_sync_status" in source
