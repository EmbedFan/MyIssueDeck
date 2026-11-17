"""The small pure functions of the installer."""

from __future__ import annotations

import os
import sqlite3
import stat

import pytest

from .conftest import NEW_VERSION, write_manifest


@pytest.mark.parametrize(("a", "b", "expected"), [
    ("0.10.0", "0.9.0", 1),       # numeric, not text, order: the very bug a text compare has
    ("0.9.0", "0.10.0", -1),
    ("1.2.0", "1.2.0", 0),
    ("1.2", "1.2.0", 0),
    ("v1.3.0", "1.2.9", 1),
    ("2.0.0rc1", "1.9.9", 1),
])
def test_versions_are_compared_numerically(mod, a, b, expected):
    assert mod.compare_versions(a, b) == expected


def test_a_text_that_is_not_a_version_is_rejected(mod):
    with pytest.raises(ValueError):
        mod.parse_version("latest")


def test_python_tag(mod):
    assert mod.python_tag((3, 12)) == "cp312"
    assert mod.python_tag((3, 11)) == "cp311"


def test_top_level_keys_ignore_comments_and_keys_inside_tables(mod):
    text = '# port = 1\nhost = "x"\nport = 2\n\n[[tokens]]\nname = "a"\n\n[sqlite]\nbusy = 1\n'

    assert mod.top_level_keys(text) == {"host", "port", "[tokens]", "[sqlite]"}


def test_a_read_only_tree_can_be_removed(mod, tmp_path):
    """Old package files were read-only and an upgrade failed with 'access denied'."""
    tree = tmp_path / "old-env"
    (tree / "Lib" / "pkg" / "licenses").mkdir(parents=True)
    files = [tree / "Lib" / "pkg" / "licenses" / "LICENSE", tree / "Lib" / "pkg" / "mod.py"]
    for file in files:
        file.write_text("x", encoding="utf-8")
        os.chmod(file, stat.S_IREAD)

    mod.remove_tree(tree)

    assert not tree.exists()


def test_removing_a_missing_tree_is_not_an_error(mod, tmp_path):
    mod.remove_tree(tmp_path / "nothing")


def test_sqlite_backup_is_a_consistent_copy_of_a_database_in_use(mod, tmp_path):
    source = tmp_path / "live.db"
    conn = sqlite3.connect(source)
    conn.execute("pragma journal_mode=wal")
    conn.execute("create table t (v text)")
    conn.execute("insert into t values ('kept')")
    conn.commit()  # still open: -wal and -shm exist

    mod.backup_sqlite(source, tmp_path / "copy" / "backup.db")

    copy = sqlite3.connect(tmp_path / "copy" / "backup.db")
    assert copy.execute("select v from t").fetchall() == [("kept",)]
    copy.close()
    conn.close()


def test_manifest_verification_accepts_the_untouched_content(mod, make):
    installer, _, _ = make()

    installer.verify_content()  # no exception


def test_a_changed_file_makes_the_installer_refuse_with_the_damaged_code(mod, make, source):
    (source / "payload" / "start-server.ps1").write_text("tampered", encoding="utf-8")
    installer, _, _ = make()

    with pytest.raises(mod.InstallError) as error:
        installer.verify_content()

    assert error.value.code == mod.EXIT_DAMAGED
    assert "start-server.ps1" in str(error.value)


def test_a_missing_file_makes_the_installer_refuse(mod, make, source):
    (source / "wheelhouse" / "common" / "pure-1.0-py3-none-any.whl").unlink()
    installer, _, _ = make()

    with pytest.raises(mod.InstallError) as error:
        installer.verify_content()

    assert error.value.code == mod.EXIT_DAMAGED


def test_the_version_comes_from_the_manifest(mod, make, source):
    write_manifest(source, "1.2.0")
    installer, _, _ = make()

    assert installer.version == "1.2.0" == NEW_VERSION
    assert installer.report.new_version == "1.2.0"


def test_without_a_manifest_the_version_comes_from_the_wheel_name(mod, make, source):
    (source / mod.MANIFEST).unlink()
    installer, _, _ = make()

    assert installer.version == NEW_VERSION


def test_starting_a_long_running_program_does_not_wait_for_it(mod):
    """The server start script leaves the server running; its children inherit the output
    pipes. Capturing output made the installer wait until the server stopped (a hang found on
    the real machine), so the scripts are run without capturing."""
    import sys
    import time

    code = (
        "import subprocess, sys;"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)']);"
        "sys.exit(3)"
    )
    started = time.monotonic()

    result = mod.Runner().run([sys.executable, "-c", code], capture=False, timeout=20)

    assert result.returncode == 3
    assert time.monotonic() - started < 8


def test_the_server_scripts_are_run_without_capturing_their_output(mod, tmp_path):
    class Spy:
        def __init__(self):
            self.kwargs = []

        def run(self, command, cwd=None, timeout=None, capture=True):
            import subprocess

            self.kwargs.append(capture)
            return subprocess.CompletedProcess(command, 0, "", "")

    spy = Spy()
    control = mod.ServerControl(spy)

    control.start(tmp_path)
    control.stop(tmp_path)

    assert spy.kwargs == [False, False]
