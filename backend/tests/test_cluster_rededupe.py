from api.ui_router import _row_entries_for_rededupe
from infrastructure.naming.enriched_name import collapse_cluster_rows


def test_row_entries_for_rededupe_expands_members() -> None:
    row = {
        "enriched_name": "Brand filter X",
        "aliases": ["a1", "a2"],
        "values": {"бренд": "Brand"},
        "members": [
            {"item": "a1", "values": {"бренд": "Brand"}, "source": "ai"},
            {"item": "a2", "values": {"бренд": "Brand"}, "source": "memory"},
        ],
    }
    entries = _row_entries_for_rededupe(row, "{бренд} filter")
    assert len(entries) == 2
    assert entries[0]["item"] == "a1"
    assert entries[0]["enriched_name"] == "Brand filter"


def test_collapse_after_rededupe_flow() -> None:
    template = "{бренд}"
    entries = _row_entries_for_rededupe(
        {
            "enriched_name": "A",
            "item": "item-1",
            "aliases": ["item-1", "item-2"],
            "values": {"бренд": "X"},
        },
        template,
    )
    embeddings = [[1.0, 0.0], [0.99, 0.01]]
    collapsed = collapse_cluster_rows(entries, embeddings, threshold=0.15)
    assert len(collapsed) == 1
    assert set(collapsed[0]["aliases"]) == {"item-1", "item-2"}
