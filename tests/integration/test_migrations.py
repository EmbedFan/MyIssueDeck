import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(Path.cwd() / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_upgrade_head_creates_all_tables(tmp_path):
    db = tmp_path / "t.db"
    command.upgrade(_alembic_config(db), "head")

    engine = create_engine(f"sqlite:///{db}")
    names = set(inspect(engine).get_table_names())
    expected = {
        "items", "item_tags", "item_applies_to",
        "ship_records", "ship_commits", "item_relationships", "item_events",
        "item_external_links", "work_sessions", "work_session_updates",
        "import_batches",
        "items_fts", "alembic_version",
    }
    assert expected.issubset(names)
    item_columns = {column["name"] for column in inspect(engine).get_columns("items")}
    assert "custom_fields_json" in item_columns


def test_fts5_triggers_sync_on_insert(tmp_path):
    db = tmp_path / "t.db"
    command.upgrade(_alembic_config(db), "head")
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO items (project_key, local_id, kind, status, title, "
            "body, custom_fields_json, created_at, updated_at) VALUES "
            "('p', 'FEAT-0001', 'feature', 'proposed', 'hello world',"
            " 'some body text', '{}', 't', 't')"
        ))
        hits = conn.execute(text(
            "SELECT rowid FROM items_fts WHERE items_fts MATCH 'hello'"
        )).scalars().all()
    assert len(hits) == 1


def test_0007_backfills_default_estimated_time_only_where_missing(tmp_path):
    db = tmp_path / "t.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "0006")
    engine = create_engine(f"sqlite:///{db}")
    rows = [
        ("FEAT-0001", "{}"),
        ("FEAT-0002", '{"priority": "high"}'),
        ("FEAT-0003", '{"estimated_time": 4}'),
        ("FEAT-0004", '{"estimated_time": 0}'),
        ("FEAT-0005", "not json"),
    ]
    with engine.begin() as conn:
        for local_id, fields in rows:
            conn.execute(
                text(
                    "INSERT INTO items (project_key, local_id, kind, status, title, "
                    "body, custom_fields_json, created_at, updated_at) VALUES "
                    "('p', :local_id, 'feature', 'proposed', 't', '', :fields, "
                    "'created', 'updated')"
                ),
                {"local_id": local_id, "fields": fields},
            )

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        result = {
            local_id: (json.loads(fields), updated_at)
            for local_id, fields, updated_at in conn.execute(
                text("SELECT local_id, custom_fields_json, updated_at FROM items")
            )
        }
    assert result["FEAT-0001"][0] == {"estimated_time": 0.5}
    assert result["FEAT-0002"][0] == {"priority": "high", "estimated_time": 0.5}
    assert result["FEAT-0003"][0] == {"estimated_time": 4}
    assert result["FEAT-0004"][0] == {"estimated_time": 0}
    assert result["FEAT-0005"][0] == {"estimated_time": 0.5}
    assert {updated for _, updated in result.values()} == {"updated"}


def test_downgrade_drops_tables(tmp_path):
    db = tmp_path / "t.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = create_engine(f"sqlite:///{db}")
    names = set(inspect(engine).get_table_names())
    assert "items" not in names
