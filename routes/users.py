"""
User listing, role overrides, license debug
"""
from __future__ import annotations
import logging
import traceback
from flask import Blueprint, jsonify, request
from routes import state
from app_config import (
    _load_role_overrides, _save_role_overrides, _resolve_display_name,
)

bp = Blueprint("users", __name__)
logger = logging.getLogger(__name__)


@bp.route("/api/users")
def get_users():
    """List all tenant users for account selection."""
    if not state.connector:
        return jsonify({"error": "not authenticated"}), 401
    try:
        users   = state.connector.list_users()
        out     = []
        seen    = set()

        # Build SKU map for role classification.
        # get_subscribed_skus() tries /subscribedSkus → /me/licenseDetails.
        # Then always merge per-user licenseDetails on top — this ensures we
        # have skuPartNumbers for every distinct SKU in the tenant, not just
        # the admin's own license (which is all /me/licenseDetails returns).
        try:
            sku_map = state.connector.get_subscribed_skus()
        except Exception:
            sku_map = {}

        try:
            per_user = state.connector.build_sku_map_from_users(users)
            if per_user:
                added = len(set(per_user) - set(sku_map))
                sku_map.update(per_user)
                if added:
                    logger.info("[skus] merged %d additional SKU(s) from per-user licenseDetails", added)
        except Exception:
            pass

        # Load any manual role overrides set by the admin
        _role_overrides = _load_role_overrides()

        def _build_user(u: dict, is_me: bool = False) -> dict:
            _em   = u.get("mail") or u.get("userPrincipalName", "")
            _auto = state.connector.classify_user_role(
                u.get("assignedLicenses", []), sku_map
            )
            # Manual override takes precedence over auto-classification
            _role = _role_overrides.get(u["id"], _auto)
            return {
                "id":           u["id"],
                "displayName":  _resolve_display_name(u.get("displayName", ""), _em),
                "email":        _em,
                "isMe":         is_me,
                "userRole":     _role,
                "roleOverride": u["id"] in _role_overrides,
            }

        if state.connector.is_app_mode:
            for u in users:
                uid = u.get("id")
                if uid and uid not in seen:
                    seen.add(uid)
                    out.append(_build_user(u))
        else:
            me    = state.connector.get_user_info()
            me_id = me.get("id")
            for u in ([me] + users):
                uid = u.get("id")
                if uid and uid not in seen:
                    seen.add(uid)
                    out.append(_build_user(u, is_me=(uid == me_id)))

        # Log a warning when no users were classified — helps diagnose
        # tenants with SKUs not yet in m365_skus.json
        classified = [u for u in out if u["userRole"] in ("student", "staff")]
        if out and not classified:
            unknown_skus: set = set()
            for u in users[:20]:  # sample first 20 to keep it brief
                for lic in u.get("assignedLicenses", []):
                    sid = lic.get("skuId", "")
                    if sid:
                        unknown_skus.add(sid)
            logger.warning(
                "[role] 0/%d users classified — no SKUs in m365_skus.json matched. "
                "Unrecognised SKU IDs (sample): %s. "
                "Add them to classification/m365_skus.json or use /api/users/license_debug.",
                len(out), sorted(unknown_skus)[:10],
            )

        return jsonify({
            "users":             out,
            "sku_map_available": bool(sku_map),
            "unclassified":      len(out) - len(classified),
        })
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@bp.route("/api/users/license_debug")
def license_debug():
    """Full diagnostic: runtime SKU sets, sku_map, per-user trace, and step-by-step
    classification walk for every user — enough to diagnose any remaining issue."""
    if not state.connector:
        return jsonify({"error": "not authenticated"}), 401
    try:
        users   = state.connector.list_users()
        sku_map = state.connector.get_subscribed_skus()
        try:
            sku_map.update(state.connector.build_sku_map_from_users(users))
        except Exception:
            pass

        # Per-user trace with step-by-step classification walk
        out = []
        for u in users[:100]:
            lics     = u.get("assignedLicenses", [])
            role     = state.connector.classify_user_role(lics, sku_map)

            # Walk each licence exactly as classify_user_role does
            lic_trace = []
            for lic in lics:
                raw_id  = lic.get("skuId", "")
                low_id  = raw_id.lower()
                name    = sku_map.get(low_id) or sku_map.get(raw_id) or "?"
                lic_trace.append({
                    "skuId":       raw_id,
                    "skuName":     name,
                    "in_staff":    low_id in state.connector._STAFF_SKU_IDS,
                    "in_student":  low_id in state.connector._STUDENT_SKU_IDS,
                    "frag_staff":  next((f for f in state.connector._STAFF_SKU_FRAGMENTS
                                        if f in name.upper()), None),
                    "frag_student": next((f for f in state.connector._STUDENT_SKU_FRAGMENTS
                                         if f in name.upper()), None),
                })

            out.append({
                "displayName": u.get("displayName", ""),
                "email":       u.get("mail") or u.get("userPrincipalName", ""),
                "role":        role,
                "licences":    lic_trace,
            })

        return jsonify({
            # Runtime state — proves whether m365_skus.json loaded correctly
            "runtime": {
                "student_ids_count": len(state.connector._STUDENT_SKU_IDS),
                "staff_ids_count":   len(state.connector._STAFF_SKU_IDS),
                "student_fragments": list(state.connector._STUDENT_SKU_FRAGMENTS),
                "staff_fragments":   list(state.connector._STAFF_SKU_FRAGMENTS),
                "sku_map_entries":   len(sku_map),
                "sku_file_path":     str(state.connector._sku_file_path()),
            },
            "student_ids": sorted(state.connector._STUDENT_SKU_IDS),
            "staff_ids":   sorted(state.connector._STAFF_SKU_IDS),
            "sku_map":     sku_map,
            "users":       out,
        })
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@bp.route("/api/users/lookup")
def lookup_user():
    """Look up a single user by UPN or email."""
    if not state.connector:
        return jsonify({"error": "not authenticated"}), 401
    upn = request.args.get("upn", "").strip()
    if not upn:
        return jsonify({"error": "upn required"}), 400
    try:
        data   = state.connector._get(f"/users/{upn}", {"$select": "id,displayName,mail,userPrincipalName"})
        _email = data.get("mail") or data.get("userPrincipalName", upn)
        return jsonify({
            "id":          data["id"],
            "displayName": _resolve_display_name(data.get("displayName", ""), _email, upn),
            "email":       _email,
            "isMe":        False,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/api/users/role_override", methods=["GET"])
def role_override_get():
    """Return all manual role overrides as {user_id: role}."""
    return jsonify(_load_role_overrides())


@bp.route("/api/users/role_override", methods=["POST"])
def role_override_set():
    """Set or clear a manual role override for one user.

    Body: {user_id, role}  — role is 'student' | 'staff' | 'other' | '' (clear).
    """
    data    = request.get_json() or {}
    uid     = data.get("user_id", "").strip()
    role    = data.get("role", "").strip().lower()
    if not uid:
        return jsonify({"error": "user_id required"}), 400
    if role and role not in ("student", "staff", "other"):
        return jsonify({"error": "role must be student | staff | other | '' (clear)"}), 400
    overrides = _load_role_overrides()
    if role:
        overrides[uid] = role
    else:
        overrides.pop(uid, None)
    _save_role_overrides(overrides)
    return jsonify({"ok": True, "user_id": uid, "role": role or None,
                    "total_overrides": len(overrides)})
