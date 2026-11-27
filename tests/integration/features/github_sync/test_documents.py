"""FEA-0012 phase 4: the documents of a project travel through the GitHub repository."""

import json

import pytest

from issuedeck.features.documents.service import DocumentService
from issuedeck.features.github_sync.service import import_project

from .fake_github import FakeGitHub
from .test_service import (  # noqa: F401
    ENV,
    _export,
    _new_target,
    _settings,
    session_and_registry,
    source,
)


@pytest.fixture
async def with_documents(source, tmp_path):  # noqa: F811
    session, registry = source
    registry.server.data_dir = tmp_path / "source-data"
    documents = DocumentService(registry.server.data_dir / "documents", registry)
    documents.create("p", "Feature request.md", "# Request\n", kind="request")
    documents.create("p", "My prompt", "Do the thing\n", kind="prompt")
    return session, registry, documents


async def _import(tmp_path, fake, name="target"):
    engine, Session, target = await _new_target(tmp_path, name)
    target.server.data_dir = tmp_path / f"{name}-data"
    async with Session() as other:
        report, _commit = await import_project(
            session=other, registry=target, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
        )
    await engine.dispose()
    return report, tmp_path / f"{name}-data" / "documents" / "p"


async def test_the_export_uploads_the_document_files_and_the_list(with_documents):
    fake = FakeGitHub()

    report = await _export(with_documents[:2], fake)

    files = fake.files()
    assert json.loads(files["p/documents/DOC-0001.json"])["name"] == "Feature request.md"
    assert json.loads(files["p/documents/DOC-0002.json"])["body"] == "Do the thing\n"
    assert json.loads(files["p/documents.json"]) == {"ids": ["DOC-0001", "DOC-0002"],
                                                      "next_id": 3}
    assert "documents.json" in report.files_changed
    assert "documents/DOC-0001.json" in report.files_changed


async def test_a_second_export_changes_nothing_and_a_change_uploads_only_that_document(
        with_documents):
    session, registry, documents = with_documents
    fake = FakeGitHub()
    await _export((session, registry), fake)
    commits = len(fake.history())

    again = await _export((session, registry), fake)
    assert again.up_to_date is True and len(fake.history()) == commits

    documents.append("p", "DOC-0002", "one more line")
    changed = await _export((session, registry), fake)

    assert sorted(changed.files_changed) == ["documents/DOC-0002.json", "manifest.json"]


async def test_the_documents_come_back_from_the_repository(with_documents, tmp_path):
    session, registry, _documents = with_documents
    fake = FakeGitHub()
    await _export((session, registry), fake)

    report, folder = await _import(tmp_path, fake)

    assert (report.documents_added, report.documents_skipped, report.warnings) == (2, 0, [])
    stored = json.loads((folder / "DOC-0001.json").read_text(encoding="utf-8"))
    assert (stored["name"], stored["kind"], stored["body"]) == (
        "Feature request.md", "request", "# Request\n")
    assert (folder / "DOC-0001.json").read_bytes() == \
        fake.files()["p/documents/DOC-0001.json"]  # byte for byte


async def test_a_deleted_document_does_not_come_back_from_its_leftover_file(
        with_documents, tmp_path):
    session, registry, documents = with_documents
    fake = FakeGitHub()
    await _export((session, registry), fake)
    documents.delete("p", "DOC-0002")

    again = await _export((session, registry), fake)

    # an export only adds and changes files: the file stays, but the list no longer names it
    assert "p/documents/DOC-0002.json" in fake.files()
    assert json.loads(fake.files()["p/documents.json"])["ids"] == ["DOC-0001"]
    assert "documents.json" in again.files_changed
    report, folder = await _import(tmp_path, fake)
    assert (report.documents_added, report.documents_skipped, report.warnings) == (1, 0, [])
    assert sorted(p.name for p in folder.iterdir()) == ["DOC-0001.json", "documents.json"]


async def test_the_links_between_documents_and_items_travel_too(with_documents, tmp_path):
    from sqlalchemy import select

    from issuedeck.features.documents.link_repo import ItemDocumentRepo
    from issuedeck.features.documents.link_service import ItemDocumentService
    from issuedeck.features.items.models import ItemDocument
    from issuedeck.features.items.repo import ItemRepo

    session, registry, documents = with_documents
    links = ItemDocumentService(
        documents, ItemRepo(session), ItemDocumentRepo(session), registry, session)
    await links.link("p", "FEAT-0001", "DOC-0001")
    fake = FakeGitHub()
    report = await _export((session, registry), fake)

    assert "item_documents.json" in report.files_changed
    assert json.loads(fake.files()["p/item_documents.json"])[0]["document_id"] == "DOC-0001"

    engine, Session, target = await _new_target(tmp_path, "linked")
    target.server.data_dir = tmp_path / "linked-data"
    async with Session() as other:
        imported, _commit = await import_project(
            session=other, registry=target, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
        )
        rows = (await other.execute(select(ItemDocument.document_id))).scalars().all()
    await engine.dispose()

    assert (imported.documents_added, imported.item_documents_added) == (2, 1)
    assert rows == ["DOC-0001"]
