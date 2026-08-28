from frc_arch_modeler.persistence.layout_store import LayoutStore


def test_layout_store_preserves_optional_ui_preferences(tmp_path) -> None:
    store = LayoutStore(tmp_path)
    layout = {"element": {"x": 12, "y": 8, "minimized": False}}

    store.save(layout, {"windowWidth": 1440, "detailsWidth": 360})

    assert store.load() == layout
    assert store.load_ui() == {"windowWidth": 1440, "detailsWidth": 360}


def test_layout_store_reads_legacy_layout_without_ui_preferences(tmp_path) -> None:
    store = LayoutStore(tmp_path)
    store.layout_path.parent.mkdir()
    store.layout_path.write_text(
        '{"schemaVersion": 1, "elements": {"element": {}}}', encoding="utf-8"
    )

    assert store.load() == {"element": {}}
    assert store.load_ui() == {}
