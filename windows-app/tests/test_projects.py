from core import backup, projects
from core.config import ConfigStore
from core.service import BackupService


def _make_tree(root):
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("value = 1", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_bytes(b"0" * 9000)
    return root


def test_resolve_names_folders_and_flags_missing_paths(tmp_path):
    real = _make_tree(tmp_path / "api")

    sources = projects.resolve([str(real), str(tmp_path / "gone")])

    assert [s.name for s in sources] == ["api", "gone"]
    assert sources[0].exists and not sources[1].exists


def test_resolve_disambiguates_two_folders_with_the_same_name(tmp_path):
    first = tmp_path / "a" / "api"
    second = tmp_path / "b" / "api"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    names = [s.name for s in projects.resolve([str(first), str(second)])]

    assert names[0] == "api"
    assert names[1] != "api", "the second folder must not overwrite the first"


def test_measure_ignores_reinstallable_directories(tmp_path):
    source = projects.resolve([str(_make_tree(tmp_path / "api"))])[0]

    size = projects.measure(source)

    # 9 KB of node_modules must not be counted; the small real files are.
    assert 0 < size < 1000


def test_collect_keeps_git_history_and_drops_node_modules(fake_root, tmp_path):
    sources = projects.resolve([str(_make_tree(tmp_path / "api"))])

    results = projects.collect(sources)

    assert results[0].ok
    mirrored = fake_root / "Projects" / "api"
    assert (mirrored / "src" / "app.py").read_text(encoding="utf-8") == "value = 1"
    assert (mirrored / ".git" / "HEAD").exists(), ".git is the most valuable part of a tree"
    assert not (mirrored / "node_modules").exists()
    assert (fake_root / "Projects" / "_sources.txt").exists()


def test_missing_folder_is_reported_not_raised(fake_root, tmp_path):
    sources = projects.resolve([str(tmp_path / "never-existed")])

    results = projects.collect(sources)

    assert not results[0].ok
    assert results[0].bytes_copied == 0


def test_scheduled_backup_refreshes_projects_first(fake_root, tmp_path):
    """The whole point: code written since the last transfer must still be in
    the archive that a timer produces."""
    tree = _make_tree(tmp_path / "api")
    store = ConfigStore()
    store.update(
        project_sources=[str(tree)],
        sync_projects_before_backup=True,
        backup_dir=str(tmp_path / "D"),
        skip_unchanged=False,
        cloud_enabled=False,
    )
    service = BackupService(store)

    # Write a file *after* configuration, as if the user had just saved it.
    (tree / "src" / "just_written.py").write_text("urgent = True", encoding="utf-8")
    summary = service.run_once()

    assert summary.ok, summary.message
    import zipfile

    with zipfile.ZipFile(summary.archive) as archive:
        names = archive.namelist()
    assert any(name.endswith("Projects/api/src/just_written.py") for name in names)
    assert not any("node_modules" in name for name in names)
