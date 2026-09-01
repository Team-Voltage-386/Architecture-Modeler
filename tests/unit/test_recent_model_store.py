from frc_arch_modeler.persistence.recent_model_store import RecentModelStore


def test_recent_model_store_round_trips(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    store = RecentModelStore(home)
    model_root = tmp_path / "models" / "Competition Robot"

    assert store.load() is None

    store.save(model_root)

    assert store.store_path == home / ".architecture_model.json"
    assert store.load() == model_root


def test_recent_model_store_overwrites_the_previous_entry(tmp_path) -> None:
    store = RecentModelStore(tmp_path)

    store.save(tmp_path / "first")
    store.save(tmp_path / "second")

    assert store.load() == tmp_path / "second"


def test_recent_model_store_ignores_a_corrupt_file(tmp_path) -> None:
    store = RecentModelStore(tmp_path)
    store.store_path.write_text("not json", encoding="utf-8")

    assert store.load() is None
