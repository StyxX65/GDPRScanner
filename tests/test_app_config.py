"""
test_app_config.py — Tests for app_config.py.

Covers:
  - LANG loading and key access
  - Article 9 keyword detection (_check_special_category)
  - Config load/save round-trip
  - Admin PIN hash/verify
  - Profile CRUD (_profile_save, _profile_get, _profile_delete)
  - SMTP password encryption/decryption round-trip
"""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import app_config


# ─────────────────────────────────────────────────────────────────────────────
# 1. i18n
# ─────────────────────────────────────────────────────────────────────────────

class TestLang:

    def test_lang_dict_loaded(self):
        assert isinstance(app_config.LANG, dict)
        assert len(app_config.LANG) > 0

    def test_lang_has_lang_code(self):
        assert "_lang_code" in app_config.LANG

    def test_load_lang_returns_dict(self):
        lang = app_config._load_lang()
        assert isinstance(lang, dict)

    def test_load_lang_forced_en(self):
        lang = app_config._load_lang_forced("en")
        assert isinstance(lang, dict)
        assert len(lang) > 0

    def test_load_lang_forced_da(self):
        lang = app_config._load_lang_forced("da")
        assert isinstance(lang, dict)
        assert len(lang) > 0

    def test_load_lang_forced_de(self):
        lang = app_config._load_lang_forced("de")
        assert isinstance(lang, dict)
        assert len(lang) > 0

    def test_missing_lang_falls_back(self):
        # Unknown lang code should fall back without raising
        lang = app_config._load_lang_forced("xx")
        assert isinstance(lang, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Article 9 keyword detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckSpecialCategory:

    def _cats(self, text):
        cprs = [{"raw": "290472-1234"}]
        return app_config._check_special_category(text, cprs)

    def test_health_keyword_detected(self):
        cats = self._cats("CPR: 290472-1234 har diagnosen diabetes og behandling")
        assert "health" in cats

    def test_trade_union_keyword_detected(self):
        cats = self._cats("CPR: 290472-1234 er fagforeningsmedlem tillidsrepræsentant")
        assert "trade_union" in cats

    def test_religion_keyword_detected(self):
        cats = self._cats("CPR: 290472-1234 kirke konfirmation")
        assert "religion" in cats

    def test_no_keyword_returns_empty(self):
        cats = self._cats("CPR: 290472-1234 bor i Aarhus")
        assert cats == []

    def test_empty_text_returns_empty(self):
        cats = app_config._check_special_category("", [])
        assert cats == []

    def test_keyword_without_cpr_still_detected(self):
        # No CPR — keyword still triggers if no CPR list given
        cats = app_config._check_special_category("diagnose sygemelding behandling", [])
        assert "health" in cats

    def test_returns_sorted_list(self):
        cats = self._cats("CPR 290472-1234 diabetes fagforening")
        assert cats == sorted(cats)

    def test_compiled_keywords_populated(self):
        assert len(app_config._compiled_keywords) > 0

    def test_keyword_flat_has_entries(self):
        assert len(app_config._keyword_flat) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Config load / save
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:

    def test_load_config_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        cfg = app_config._load_config()
        assert isinstance(cfg, dict)

    def test_save_and_load_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        app_config._save_config({"client_id": "test-id", "tenant_id": "test-tid"})
        cfg = app_config._load_config()
        assert cfg["client_id"] == "test-id"
        assert cfg["tenant_id"] == "test-tid"

    def test_save_config_creates_file(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        monkeypatch.setattr(app_config, "_CONFIG_FILE", cfg_path)
        app_config._save_config({"x": 1})
        assert cfg_path.exists()

    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "nonexistent.json")
        cfg = app_config._load_config()
        assert cfg == {}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Admin PIN
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminPin:

    def test_pin_not_set_initially(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        # Fresh config — no PIN
        app_config._save_config({})
        assert app_config._admin_pin_is_set() is False

    def test_set_and_verify_pin(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        app_config._save_config({})
        app_config._set_admin_pin("1234")
        assert app_config._verify_admin_pin("1234") is True

    def test_wrong_pin_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        app_config._save_config({})
        app_config._set_admin_pin("1234")
        assert app_config._verify_admin_pin("9999") is False

    def test_pin_is_set_after_setting(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_CONFIG_FILE", tmp_path / "config.json")
        app_config._save_config({})
        app_config._set_admin_pin("5678")
        assert app_config._admin_pin_is_set() is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Profiles
# ─────────────────────────────────────────────────────────────────────────────

class TestProfiles:

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_SETTINGS_PATH", tmp_path / "settings.json")

    def test_profiles_load_returns_list(self):
        profiles = app_config._profiles_load()
        assert isinstance(profiles, list)

    def test_save_and_get_profile(self):
        profile = {
            "id": "test-uuid-1",
            "name": "Test Profile",
            "sources": ["email"],
            "user_ids": "all",
            "options": {},
        }
        app_config._profile_save(profile)
        loaded = app_config._profile_get("Test Profile")
        assert loaded is not None
        assert loaded["name"] == "Test Profile"

    def test_profile_get_by_id(self):
        profile = {"id": "uid-42", "name": "By ID", "sources": [], "options": {}}
        app_config._profile_save(profile)
        loaded = app_config._profile_get("uid-42")
        assert loaded is not None

    def test_profile_delete(self):
        profile = {"id": "del-1", "name": "To Delete", "sources": [], "options": {}}
        app_config._profile_save(profile)
        deleted = app_config._profile_delete("To Delete")
        assert deleted is True
        assert app_config._profile_get("To Delete") is None

    def test_delete_nonexistent_returns_false(self):
        assert app_config._profile_delete("Does Not Exist") is False

    def test_profiles_load_after_save(self):
        app_config._profile_save({"id": "p1", "name": "P1", "sources": [], "options": {}})
        app_config._profile_save({"id": "p2", "name": "P2", "sources": [], "options": {}})
        profiles = app_config._profiles_load()
        names = [p["name"] for p in profiles]
        assert "P1" in names
        assert "P2" in names


# ─────────────────────────────────────────────────────────────────────────────
# 6. SMTP password encryption
# ─────────────────────────────────────────────────────────────────────────────

class TestFernet:

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_config, "_MACHINE_ID_PATH", tmp_path / "machine_id")

    def test_encrypt_decrypt_round_trip(self):
        fernet = app_config._get_fernet()
        if fernet is None:
            pytest.skip("cryptography not installed")
        plaintext = "my-secret-smtp-password"
        encrypted = app_config._encrypt_password(plaintext)
        decrypted = app_config._decrypt_password(encrypted)
        assert decrypted == plaintext

    def test_encrypt_returns_string(self):
        fernet = app_config._get_fernet()
        if fernet is None:
            pytest.skip("cryptography not installed")
        result = app_config._encrypt_password("test")
        assert isinstance(result, str)

    def test_encrypted_differs_from_plaintext(self):
        fernet = app_config._get_fernet()
        if fernet is None:
            pytest.skip("cryptography not installed")
        enc = app_config._encrypt_password("password123")
        assert enc != "password123"

    def test_decrypt_empty_returns_empty(self):
        result = app_config._decrypt_password("")
        assert result == ""
