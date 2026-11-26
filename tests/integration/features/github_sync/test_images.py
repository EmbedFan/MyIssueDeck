"""FEA-0013 phase 5: the images of a project travel through the GitHub repository."""

import json

import pytest

from issuedeck.core.config import ImagesConfig
from issuedeck.features.github_sync.service import import_project
from issuedeck.features.images.link_repo import ItemImageRepo
from issuedeck.features.images.link_service import ItemImageService
from issuedeck.features.images.service import ImageService
from issuedeck.features.items.repo import ItemRepo

from .fake_github import FakeGitHub
from .test_service import (  # noqa: F401
    ENV,
    _export,
    _new_target,
    _settings,
    session_and_registry,
    source,
)

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'.encode()
SVG_B = f'<svg {NS}><circle r="2"/></svg>'.encode()


@pytest.fixture
async def with_images(source, tmp_path):  # noqa: F811
    session, registry = source
    registry.server.data_dir = tmp_path / "source-data"
    images = ImageService(registry.server.data_dir / "images", ImagesConfig(), registry)
    images.upload("p", "pump.svg", SVG_A)
    images.upload("p", "valve.svg", SVG_B)
    links = ItemImageService(
        images, ItemRepo(session), ItemImageRepo(session), registry, session,
    )
    await links.link("p", "FEAT-0001", "IMG-0001")
    await links.link("p", "FEAT-0002", "IMG-0002")
    return session, registry, images


async def test_the_export_uploads_the_image_files_and_the_registry(with_images):
    fake = FakeGitHub()

    report = await _export(with_images[:2], fake)

    files = fake.files()
    assert files["p/images/IMG-0001.svg"] == SVG_A
    assert files["p/images/IMG-0002.svg"] == SVG_B
    assert json.loads(files["p/images.json"])["next_id"] == 3
    assert len(json.loads(files["p/item_images.json"])) == 2
    assert "images.json" in report.files_changed
    assert "images/IMG-0001.svg" in report.files_changed


async def test_a_second_export_changes_nothing_and_a_new_image_uploads_only_itself(with_images):
    session, registry, images = with_images
    fake = FakeGitHub()
    await _export((session, registry), fake)
    commits = len(fake.history())

    again = await _export((session, registry), fake)
    assert again.up_to_date is True and len(fake.history()) == commits

    images.upload("p", "third.svg", f'<svg {NS}><path d="M0 0L5 5"/></svg>'.encode())
    third = await _export((session, registry), fake)

    assert sorted(third.files_changed) == ["images.json", "images/IMG-0003.svg", "manifest.json"]


async def test_the_images_come_back_from_the_repository(with_images, tmp_path):
    session, registry, _images = with_images
    fake = FakeGitHub()
    await _export((session, registry), fake)
    engine, Session, target = await _new_target(tmp_path)
    target.server.data_dir = tmp_path / "target-data"
    async with Session() as other:
        report, _commit = await import_project(
            session=other, registry=target, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
        )
    await engine.dispose()

    assert (report.images_added, report.item_images_added) == (2, 2)
    store = tmp_path / "target-data" / "images" / "p"
    assert (store / "IMG-0001.svg").read_bytes() == SVG_A
    assert (store / "IMG-0002.svg").read_bytes() == SVG_B


async def test_an_image_file_the_registry_does_not_list_is_ignored_on_import(
        with_images, tmp_path):
    session, registry, _images = with_images
    fake = FakeGitHub()
    await _export((session, registry), fake)
    fake.commit_files({"p/images/IMG-0009.svg": SVG_A})  # left behind by a deleted image
    engine, Session, target = await _new_target(tmp_path)
    target.server.data_dir = tmp_path / "target-data"
    async with Session() as other:
        report, _commit = await import_project(
            session=other, registry=target, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
        )
    await engine.dispose()

    assert (report.images_added, report.images_skipped, report.warnings) == (2, 0, [])
    store = tmp_path / "target-data" / "images" / "p"
    assert sorted(path.name for path in store.iterdir()) == [
        "IMG-0001.svg", "IMG-0002.svg", "images.json"]
