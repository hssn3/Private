from datetime import datetime, timedelta

from core import backup


def _seed(root):
    (root / "Projects" / "main.py").write_text("print('hello')", encoding="utf-8")
    (root / "Apps" / "cursor").mkdir(parents=True, exist_ok=True)
    (root / "Apps" / "cursor" / "settings.json").write_text("{}", encoding="utf-8")


def test_archive_name_matches_the_rotation_pattern():
    name = backup.archive_name(datetime(2026, 8, 26, 13, 45, 0))
    assert name == "backup_0_20260826-134500.zip"
    assert backup.ARCHIVE_RE.match(name)


def test_backup_creates_an_archive_containing_folder_zero(fake_root, tmp_path):
    _seed(fake_root)
    destination = tmp_path / "D"

    result = backup.run_backup(destination, keep=10, skip_unchanged=False)

    assert result.ok, result.message
    assert result.path.exists()
    import zipfile

    with zipfile.ZipFile(result.path) as archive:
        names = archive.namelist()
    assert any(name.endswith("Projects/main.py") for name in names)
    assert all(name.startswith("0/") for name in names)


def test_cycle_rule_keeps_only_the_newest_n(tmp_path):
    destination = tmp_path / "D"
    destination.mkdir()
    base = datetime(2026, 8, 26, 10, 0, 0)
    for index in range(14):
        name = backup.archive_name(base + timedelta(minutes=10 * index))
        (destination / name).write_bytes(b"x")

    removed = backup.enforce_cycle_rule(destination, keep=10)

    remaining = backup.list_archives(destination)
    assert len(remaining) == 10
    assert len(removed) == 4
    # The survivors are the newest ten, and the oldest four are gone for good.
    assert remaining[0].name == backup.archive_name(base + timedelta(minutes=130))
    assert remaining[-1].name == backup.archive_name(base + timedelta(minutes=40))


def test_eleventh_backup_evicts_the_first(fake_root, tmp_path):
    _seed(fake_root)
    destination = tmp_path / "D"
    destination.mkdir()
    base = datetime(2026, 8, 26, 10, 0, 0)
    for index in range(10):
        (destination / backup.archive_name(base + timedelta(minutes=index))).write_bytes(b"x")
    oldest = destination / backup.archive_name(base)

    result = backup.run_backup(destination, keep=10, skip_unchanged=False)

    assert result.ok, result.message
    assert not oldest.exists()
    assert len(backup.list_archives(destination)) == 10


def test_skip_unchanged_avoids_a_second_identical_archive(fake_root, tmp_path):
    _seed(fake_root)
    destination = tmp_path / "D"

    first = backup.run_backup(destination, keep=10, skip_unchanged=True)
    second = backup.run_backup(destination, keep=10, skip_unchanged=True)

    assert first.ok and not first.skipped_unchanged
    assert second.ok and second.skipped_unchanged
    assert len(backup.list_archives(destination)) == 1


def test_changed_file_defeats_the_skip(fake_root, tmp_path):
    _seed(fake_root)
    destination = tmp_path / "D"
    backup.run_backup(destination, keep=10, skip_unchanged=True)

    (fake_root / "Projects" / "new_feature.py").write_text("x = 1", encoding="utf-8")
    again = backup.run_backup(destination, keep=10, skip_unchanged=True)

    assert again.ok and not again.skipped_unchanged
    assert len(backup.list_archives(destination)) == 2


def test_backup_destination_inside_folder_zero_is_not_swallowed(fake_root):
    _seed(fake_root)
    destination = fake_root / "SelfBackups"

    first = backup.run_backup(destination, keep=10, skip_unchanged=False)
    (fake_root / "Projects" / "later.py").write_text("y = 2", encoding="utf-8")
    second = backup.run_backup(destination, keep=10, skip_unchanged=False)

    import zipfile

    with zipfile.ZipFile(second.path) as archive:
        names = archive.namelist()
    assert first.path.name not in "".join(names)
