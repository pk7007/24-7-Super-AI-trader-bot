import tarfile

import pytest

from deploy.make_bundle import ITEMS, create_bundle, state_locks


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "bot-project"
    (root / "bot").mkdir(parents=True)
    (root / "bot/main.py").write_text("# fixture\n")
    (root / "requirements.txt").write_text("pytest==9.2.0\n")
    (root / "requirements.lock").write_text("pytest==9.2.0\n")
    for name in ITEMS:
        item = root / name
        if not item.exists():
            item.parent.mkdir(parents=True, exist_ok=True)
            if name == "tests":
                item.mkdir()
            else:
                item.write_text("# fixture\n")
    for mode in ("paper", "shadow"):
        folder = root / "state" / mode
        folder.mkdir(parents=True)
        (folder / "state.db").write_bytes(b"fixture database")
        (folder / ".env").write_text("fixture-only-do-not-include")
        (folder / "bot.lock").write_text(" ")
    return root


def test_code_bundle_includes_dependency_lock_and_excludes_state(project):
    with tarfile.open(create_bundle(project)) as archive:
        names = archive.getnames()
    assert "bot-project/requirements.lock" in names
    assert not any("/state/" in name for name in names)


def test_state_bundle_refuses_a_running_bot_and_preserves_previous_bundle(project):
    output = create_bundle(project)
    before = output.read_bytes()
    with state_locks(project):
        with pytest.raises(RuntimeError, match="running"):
            create_bundle(project, with_state=True)
    assert output.read_bytes() == before


def test_state_bundle_keeps_locks_during_tar_and_never_archives_credentials(project, monkeypatch):
    original = tarfile.TarFile.add
    checked = []

    def add(archive, name, *args, **kwargs):
        if str(name).endswith("state/paper") or str(name).endswith("state\\paper"):
            with pytest.raises(RuntimeError):
                with state_locks(project):
                    pass
            checked.append(True)
        return original(archive, name, *args, **kwargs)

    monkeypatch.setattr(tarfile.TarFile, "add", add)
    with tarfile.open(create_bundle(project, with_state=True)) as archive:
        names = archive.getnames()
    assert checked and "bot-project/state/paper/state.db" in names
    assert not any(".env" in name or name.endswith("/bot.lock") for name in names)
