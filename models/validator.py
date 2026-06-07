"""
Data validation layer — schema enforcement for player dicts at enrichment boundary.
Catches NaN/None propagation before it reaches sell logic scoring.
"""

from typing import Any

# Required fields every player dict must have
_REQUIRED = ["name", "age", "position_code"]

# Expected types for numeric fields
_NUMERIC_FIELDS = {
    "age": (int, float),
    "market_value_m": (int, float),
    "overall": (int, float),
    "pac": (int, float),
    "sho": (int, float),
    "pas": (int, float),
    "dri": (int, float),
    "def_": (int, float),
    "phy": (int, float),
    "xg_per90": (int, float),
    "xa_per90": (int, float),
}

# Valid position codes
_VALID_POSITIONS = {
    "GK", "CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB",
    "DM", "CDM", "CM", "LCM", "RCM", "CAM", "AM",
    "LW", "RW", "LM", "RM", "ST", "CF", "FW",
}


def validate_player(player: dict) -> dict:
    """
    Validate a player dict against the expected schema.
    Returns {"valid": bool, "errors": [str], "warnings": [str], "player": dict}
    Fixes what it can (type coercion), flags the rest.
    """
    errors = []
    warnings = []
    p = dict(player)  # work on a copy

    # ── Required fields ──────────────────────────────────────────────────────
    for field in _REQUIRED:
        if not p.get(field):
            errors.append(f"Missing required field: '{field}'")

    # ── Numeric coercion ─────────────────────────────────────────────────────
    for field, types in _NUMERIC_FIELDS.items():
        val = p.get(field)
        if val is None:
            warnings.append(f"Null numeric field: '{field}' — defaulting to 0")
            p[field] = 0
            continue
        try:
            p[field] = float(val) if float in types else int(val)
        except (TypeError, ValueError):
            warnings.append(f"Non-numeric value in '{field}': {val!r} — defaulting to 0")
            p[field] = 0

    # ── Position code ────────────────────────────────────────────────────────
    pos = p.get("position_code", "")
    if pos and pos.upper() not in _VALID_POSITIONS:
        warnings.append(f"Unknown position_code: '{pos}'")

    # ── Age sanity ───────────────────────────────────────────────────────────
    age = p.get("age", 0)
    if isinstance(age, (int, float)) and (age < 15 or age > 45):
        warnings.append(f"Suspicious age value: {age}")

    # ── Name sanitization ────────────────────────────────────────────────────
    name = p.get("name", "")
    if name and not isinstance(name, str):
        p["name"] = str(name)

    return {
        "valid":    len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
        "player":   p,
    }


def validate_squad(squad: list) -> list:
    """
    Validate and clean an entire squad. Drops invalid players with warnings.
    Returns cleaned list of player dicts.
    """
    cleaned = []
    for player in squad:
        result = validate_player(player)
        if result["valid"]:
            cleaned.append(result["player"])
        else:
            import logging
            logging.warning(
                f"Dropping invalid player '{player.get('name','?')}': {result['errors']}"
            )
    return cleaned
