from core import collector
from core.config import Config, ConfigStore
from core.detect import DetectedApp


def test_config_round_trips_through_disk(fake_root):
    store = ConfigStore()
    store.update(backup_dir="E:\\vault", keep_count=7, interval_minutes=15, cloud_enabled=True)

    reloaded = ConfigStore().current

    assert reloaded.backup_dir == "E:\\vault"
    assert reloaded.keep_count == 7
    assert reloaded.interval_minutes == 15
    assert reloaded.cloud_enabled is True


def test_config_ignores_unknown_keys_from_an_older_file(fake_root):
    import json

    from core import paths

    paths.config_file().write_text(
        json.dumps({"keep_count": 3, "a_setting_we_removed": True}), encoding="utf-8"
    )

    config = ConfigStore().current

    assert config.keep_count == 3
    assert not hasattr(config, "a_setting_we_removed")


def test_collect_mirrors_data_and_honours_excludes(fake_root, tmp_path):
    source = tmp_path / "CursorUser"
    (source / "Cache").mkdir(parents=True)
    (source / "Cache" / "huge.bin").write_bytes(b"0" * 5000)
    (source / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")

    app = DetectedApp(
        key="cursor", name="Cursor", category="editor", emoji="🖱️",
        exe_path=None, known=True, data_paths=[(source, "User")],
        excludes=("Cache",),
    )

    results = collector.collect([app])

    assert len(results) == 1 and results[0].ok
    mirrored = fake_root / "Apps" / "cursor" / "User"
    assert (mirrored / "settings.json").read_text(encoding="utf-8") == '{"theme":"dark"}'
    assert not (mirrored / "Cache").exists()
    assert (fake_root / "Apps" / "cursor" / "_manifest.json").exists()


def test_collect_records_apps_without_known_data(fake_root):
    app = DetectedApp(
        key="reg::something", name="Something", category="other", emoji="🧱",
        exe_path=None, known=False, data_paths=[], excludes=(),
    )

    results = collector.collect([app])

    assert results[0].ok
    assert results[0].bytes_copied == 0
