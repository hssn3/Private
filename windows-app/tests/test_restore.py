import zipfile

from core import backup, restore


def test_round_trip(fake_root, tmp_path):
    (fake_root / "Projects" / "app.py").write_text("value = 42", encoding="utf-8")
    destination = tmp_path / "D"

    made = backup.run_backup(destination, keep=5, skip_unchanged=False)
    assert made.ok

    valid, message, count, size = restore.inspect(made.path)
    assert valid, message
    assert count > 0 and size > 0

    out = tmp_path / "restored"
    result = restore.extract(made.path, out)

    assert result.ok, result.message
    assert (out / "0" / "Projects" / "app.py").read_text(encoding="utf-8") == "value = 42"


def test_inspect_rejects_a_non_zip(tmp_path):
    bogus = tmp_path / "not-a-zip.zip"
    bogus.write_text("just text", encoding="utf-8")

    valid, message, _count, _size = restore.inspect(bogus)

    assert not valid
    assert "زیپ" in message


def test_extract_refuses_traversal_entries(tmp_path):
    archive_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("0/safe.txt", "fine")
        archive.writestr("../escaped.txt", "should never land outside")

    out = tmp_path / "out"
    result = restore.extract(archive_path, out)

    assert result.ok
    assert (out / "0" / "safe.txt").exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_unsafe_names():
    assert restore._is_unsafe("../x")
    assert restore._is_unsafe("/etc/passwd")
    assert restore._is_unsafe("C:/Windows/System32/x.dll")
    assert not restore._is_unsafe("0/Apps/cursor/settings.json")
