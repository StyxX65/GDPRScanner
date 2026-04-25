"""
test_checkpoint.py — Tests for checkpoint.py.

Covers:
  - _checkpoint_key: stable hashing of scan options
  - _save_checkpoint / _load_checkpoint / _clear_checkpoint
  - _load_delta_tokens / _save_delta_tokens
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import checkpoint


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect all disk writes to a temp dir for each test."""
    monkeypatch.setattr(checkpoint, "_DATA_DIR",   tmp_path)
    monkeypatch.setattr(checkpoint, "_DELTA_PATH", tmp_path / "delta.json")


_OPTS = {
    "sources": ["email", "onedrive"],
    "user_ids": [{"id": "user-1"}, {"id": "user-2"}],
    "options": {"older_than_days": 365},
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. _checkpoint_key
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpointKey:

    def test_returns_string(self):
        key = checkpoint._checkpoint_key(_OPTS)
        assert isinstance(key, str)

    def test_key_is_hex(self):
        key = checkpoint._checkpoint_key(_OPTS)
        int(key, 16)  # raises ValueError if not hex

    def test_same_options_same_key(self):
        assert checkpoint._checkpoint_key(_OPTS) == checkpoint._checkpoint_key(_OPTS)

    def test_different_sources_different_key(self):
        opts2 = {**_OPTS, "sources": ["sharepoint"]}
        assert checkpoint._checkpoint_key(_OPTS) != checkpoint._checkpoint_key(opts2)

    def test_different_users_different_key(self):
        opts2 = {**_OPTS, "user_ids": [{"id": "user-99"}]}
        assert checkpoint._checkpoint_key(_OPTS) != checkpoint._checkpoint_key(opts2)

    def test_source_order_irrelevant(self):
        opts_a = {**_OPTS, "sources": ["email", "onedrive"]}
        opts_b = {**_OPTS, "sources": ["onedrive", "email"]}
        assert checkpoint._checkpoint_key(opts_a) == checkpoint._checkpoint_key(opts_b)

    def test_empty_options(self):
        key = checkpoint._checkpoint_key({})
        assert isinstance(key, str) and len(key) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Save / load / clear
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveLoadCheckpoint:

    def test_load_returns_none_when_no_file(self):
        key = checkpoint._checkpoint_key(_OPTS)
        assert checkpoint._load_checkpoint(key) is None

    def test_save_then_load(self):
        key = checkpoint._checkpoint_key(_OPTS)
        checkpoint._save_checkpoint(
            key,
            scanned_ids={"id1", "id2", "id3"},
            flagged=[{"id": "c1", "name": "file.docx"}],
            meta={"started_at": 1700000000},
        )
        loaded = checkpoint._load_checkpoint(key)
        assert loaded is not None

    def test_scanned_ids_preserved(self):
        key = checkpoint._checkpoint_key(_OPTS)
        checkpoint._save_checkpoint(key, {"id1", "id2"}, [], {})
        loaded = checkpoint._load_checkpoint(key)
        assert set(loaded["scanned_ids"]) == {"id1", "id2"}

    def test_flagged_items_preserved(self):
        key = checkpoint._checkpoint_key(_OPTS)
        cards = [{"id": "c1"}, {"id": "c2"}]
        checkpoint._save_checkpoint(key, set(), cards, {})
        loaded = checkpoint._load_checkpoint(key)
        assert len(loaded["flagged"]) == 2

    def test_wrong_key_returns_none(self):
        key = checkpoint._checkpoint_key(_OPTS)
        checkpoint._save_checkpoint(key, {"id1"}, [], {})
        other_opts = {**_OPTS, "sources": ["sharepoint"]}
        other_key = checkpoint._checkpoint_key(other_opts)
        assert checkpoint._load_checkpoint(other_key) is None

    def test_clear_removes_file(self, tmp_path):
        key = checkpoint._checkpoint_key(_OPTS)
        checkpoint._save_checkpoint(key, {"id1"}, [], {})
        checkpoint._clear_checkpoint()
        assert checkpoint._load_checkpoint(key) is None

    def test_clear_on_missing_file_does_not_raise(self):
        checkpoint._clear_checkpoint()  # no file exists — must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 3. Delta tokens
# ─────────────────────────────────────────────────────────────────────────────

class TestDeltaTokens:

    def test_load_returns_empty_when_no_file(self):
        assert checkpoint._load_delta_tokens() == {}

    def test_save_then_load(self):
        tokens = {
            "email:user1": "https://graph.microsoft.com/v1.0/me/mailFolders/delta?$deltaToken=abc",
            "onedrive:user1": "https://graph.microsoft.com/v1.0/me/drive/delta?token=xyz",
        }
        checkpoint._save_delta_tokens(tokens)
        loaded = checkpoint._load_delta_tokens()
        assert loaded == tokens

    def test_overwrite_preserves_new_value(self):
        checkpoint._save_delta_tokens({"key": "old_url"})
        checkpoint._save_delta_tokens({"key": "new_url"})
        assert checkpoint._load_delta_tokens()["key"] == "new_url"

    def test_save_empty_dict(self):
        checkpoint._save_delta_tokens({})
        assert checkpoint._load_delta_tokens() == {}
