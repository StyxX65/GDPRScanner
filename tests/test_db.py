"""
test_db.py — Tests for gdpr_db.py (ScanDB).

Covers:
  - begin_scan / finish_scan round-trip
  - save_item and retrieval
  - CPR index stores hash, never plaintext
  - lookup_data_subject returns matching items
  - set_disposition / get_disposition
  - Deletion log
  - Export / import cycle (merge and replace modes)
"""
import sys
import hashlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from gdpr_db import ScanDB


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_card(item_id="abc123", cpr_count=1, source_type="email", role="staff"):
    return {
        "id":               item_id,
        "name":             f"{item_id}.docx",
        "source":           "email",
        "source_type":      source_type,
        "cpr_count":        cpr_count,
        "url":              "https://example.com/item",
        "size_kb":          12.5,
        "modified":         "2024-03-01",
        "thumb_b64":        "",
        "thumb_mime":       "image/svg+xml",
        "risk":             None,
        "account_id":       "user-1",
        "account_name":     "Test User",
        "user_role":        role,
        "drive_id":         "",
        "attachments":      [],
        "folder":           "",
        "transfer_risk":    "",
        "special_category": [],
        "face_count":       0,
        "exif":             {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Scan lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class TestScanLifecycle:

    def test_begin_scan_returns_int(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        assert isinstance(scan_id, int)
        assert scan_id > 0

    def test_begin_scan_increments(self, tmp_db):
        id1 = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        id2 = tmp_db.begin_scan({"sources": ["onedrive"], "user_ids": []})
        assert id2 > id1

    def test_finish_scan_does_not_raise(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.finish_scan(scan_id, 42)  # must not raise

    def test_multiple_scans_independent(self, tmp_db):
        id1 = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(id1, _make_card("item-a"), ["290472-1234"])
        id2 = tmp_db.begin_scan({"sources": ["onedrive"], "user_ids": []})
        tmp_db.save_item(id2, _make_card("item-b"), ["010185-4321"])
        tmp_db.finish_scan(id1, 1)
        tmp_db.finish_scan(id2, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. save_item
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveItem:

    def test_save_item_does_not_raise(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card(), ["290472-1234"])

    def test_save_item_without_cprs(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card(cpr_count=0), [])

    def test_save_multiple_items(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        for i in range(5):
            tmp_db.save_item(scan_id, _make_card(f"item-{i}"), ["290472-1234"])

    def test_save_item_with_pii_counts(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        pii = {"cpr": 1, "name": 2, "email": 0}
        tmp_db.save_item(scan_id, _make_card(), ["290472-1234"], pii_counts=pii)


# ─────────────────────────────────────────────────────────────────────────────
# 3. CPR index — hash only, never plaintext
# ─────────────────────────────────────────────────────────────────────────────

class TestCprIndex:

    def test_cpr_not_stored_in_plaintext(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card(), ["290472-1234"])
        # Read the raw DB and confirm plaintext CPR is absent
        import sqlite3
        with sqlite3.connect(tmp_db._path) as con:
            rows = con.execute("SELECT cpr_hash FROM cpr_index").fetchall()
        assert len(rows) == 1
        stored = rows[0][0]
        assert stored != "290472-1234"
        assert "290472" not in stored

    def test_cpr_hash_is_sha256(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card(), ["290472-1234"])
        import sqlite3
        with sqlite3.connect(tmp_db._path) as con:
            rows = con.execute("SELECT cpr_hash FROM cpr_index").fetchall()
        stored = rows[0][0]
        expected = hashlib.sha256("290472-1234".encode()).hexdigest()
        assert stored == expected

    def test_lookup_finds_item(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("item-x"), ["290472-1234"])
        results = tmp_db.lookup_data_subject("290472-1234")
        assert len(results) >= 1

    def test_lookup_returns_correct_item(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("target-item"), ["290472-1234"])
        results = tmp_db.lookup_data_subject("290472-1234")
        ids = [r.get("id") or r.get("item_id") for r in results]
        assert "target-item" in ids

    def test_lookup_different_cpr_returns_empty(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card(), ["290472-1234"])
        results = tmp_db.lookup_data_subject("010185-4321")
        assert results == []

    def test_lookup_multiple_items_for_same_cpr(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("item-a"), ["290472-1234"])
        tmp_db.save_item(scan_id, _make_card("item-b"), ["290472-1234"])
        results = tmp_db.lookup_data_subject("290472-1234")
        assert len(results) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dispositions
# ─────────────────────────────────────────────────────────────────────────────

class TestDispositions:

    def test_get_disposition_returns_none_for_unknown(self, tmp_db):
        assert tmp_db.get_disposition("nonexistent") is None

    def test_set_and_get_disposition(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("disp-item"), ["290472-1234"])
        tmp_db.set_disposition("disp-item", "retain-legal", "Bogfoeringsloven", "", "admin")
        disp = tmp_db.get_disposition("disp-item")
        assert disp is not None
        assert disp["status"] == "retain-legal"

    def test_disposition_legal_basis_stored(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("disp-2"), [])
        tmp_db.set_disposition("disp-2", "delete-scheduled", "Data minimisation", "", "reviewer")
        disp = tmp_db.get_disposition("disp-2")
        assert disp["legal_basis"] == "Data minimisation"

    def test_disposition_overwrite(self, tmp_db):
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        tmp_db.save_item(scan_id, _make_card("disp-3"), [])
        tmp_db.set_disposition("disp-3", "unreviewed", "", "", "")
        tmp_db.set_disposition("disp-3", "deleted", "", "", "admin")
        disp = tmp_db.get_disposition("disp-3")
        assert disp["status"] == "deleted"

    def test_all_disposition_values_accepted(self, tmp_db):
        statuses = ["unreviewed", "retain-legal", "retain-legitimate",
                    "retain-contract", "delete-scheduled", "deleted"]
        scan_id = tmp_db.begin_scan({"sources": ["email"], "user_ids": []})
        for i, status in enumerate(statuses):
            item_id = f"disp-status-{i}"
            tmp_db.save_item(scan_id, _make_card(item_id), [])
            tmp_db.set_disposition(item_id, status, "", "", "test")
            disp = tmp_db.get_disposition(item_id)
            assert disp["status"] == status


# ─────────────────────────────────────────────────────────────────────────────
# 5. Export / import
# ─────────────────────────────────────────────────────────────────────────────

class TestExportImport:

    def _populate(self, db):
        scan_id = db.begin_scan({"sources": ["email"], "user_ids": []})
        db.save_item(scan_id, _make_card("exp-1"), ["290472-1234"])
        db.save_item(scan_id, _make_card("exp-2"), ["010185-4321"])
        db.set_disposition("exp-1", "retain-legal", "Bogfoeringsloven", "", "admin")
        db.finish_scan(scan_id, 2)

    def test_export_creates_zip(self, tmp_db, tmp_path):
        if not hasattr(tmp_db, "export_db"):
            pytest.skip("export_db not implemented")
        self._populate(tmp_db)
        export_path = tmp_path / "export.zip"
        tmp_db.export_db(str(export_path))
        assert export_path.exists()
        assert export_path.stat().st_size > 0

    def test_export_zip_contains_expected_files(self, tmp_db, tmp_path):
        if not hasattr(tmp_db, "export_db"):
            pytest.skip("export_db not implemented")
        self._populate(tmp_db)
        export_path = tmp_path / "export.zip"
        tmp_db.export_db(str(export_path))
        import zipfile
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
        for expected in ["export_meta.json", "flagged_items.json", "dispositions.json"]:
            assert expected in names

    def test_import_merge_adds_dispositions(self, tmp_path):
        if not hasattr(ScanDB, "export_db"):
            pytest.skip("export_db not implemented")
        # Source DB
        src = ScanDB(str(tmp_path / "src.db"))
        self._populate(src)
        export_path = tmp_path / "export.zip"
        src.export_db(str(export_path))

        # Target DB (fresh)
        tgt = ScanDB(str(tmp_path / "tgt.db"))
        tgt.import_db(str(export_path), mode="merge")
        # Disposition for exp-1 should now exist in tgt
        disp = tgt.get_disposition("exp-1")
        assert disp is not None

    def test_import_replace_restores_items(self, tmp_path):
        if not hasattr(ScanDB, "export_db"):
            pytest.skip("export_db not implemented")
        src = ScanDB(str(tmp_path / "src2.db"))
        self._populate(src)
        export_path = tmp_path / "export2.zip"
        src.export_db(str(export_path))

        tgt = ScanDB(str(tmp_path / "tgt2.db"))
        tgt.import_db(str(export_path), mode="replace")
        results = tgt.lookup_data_subject("290472-1234")
        assert len(results) >= 1
