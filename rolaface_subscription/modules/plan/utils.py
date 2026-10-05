import json
import re
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import get_datetime, get_number_format_info

from rolaface_subscription.modules.plan.constant import (
    ALLOWED_SORT_FIELDS,
    BILLING_FREQUENCIES,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    DEFAULT_STATUS,
    MAX_BILLING_CYCLES,
    MAX_DESCRIPTION_LENGTH,
    MAX_MODULES_PER_PLAN,
    MAX_NAME_LENGTH,
    MAX_PAGE,
    MAX_PAGE_SIZE,
    MAX_PLAN_CODE_LENGTH,
    MAX_PRICE,
    MAX_TRIAL_DAYS,
    MAX_USER_LIMIT,
    MSG_PLAN_NOT_FOUND,
    MSG_STALE,
    PLAN_DOCTYPE,
    PLAN_STATUSES,
    PRICE_DECIMAL_PLACES,
    PRICING_FLAT,
    PRICING_MODELS,
    RENEWAL_AUTO,
    RENEWAL_FIXED,
    RENEWAL_MODES,
    SORT_ORDERS,
)
from rolaface_subscription.utils.api_response import ConflictError

_TRUE_VALUES = {"true", "1", "yes", "y", "on", "t"}
_FALSE_VALUES = {"false", "0", "no", "n", "off", "f"}
_PLAN_CODE_RE = re.compile(r"^[A-Z0-9_-]+$")
_MONEY_QUANT = Decimal(1).scaleb(-PRICE_DECIMAL_PLACES)  # Decimal("0.01")


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _clean_str(value, field, min_len=0, max_len=None):
    if not isinstance(value, str):
        frappe.throw(f"{field} must be a string")
    value = value.strip()
    if len(value) < min_len:
        frappe.throw(f"{field} cannot be blank")
    if max_len is not None and len(value) > max_len:
        frappe.throw(f"{field} must be at most {max_len} characters")
    return value


def _to_int(value, field, minimum, maximum):
    if isinstance(value, bool):
        frappe.throw(f"{field} must be a whole number")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if "_" in text:
            frappe.throw(f"{field} must be a whole number")
        try:
            value = int(text)
        except ValueError:
            frappe.throw(f"{field} must be a whole number")
    if not isinstance(value, int) or isinstance(value, bool):
        frappe.throw(f"{field} must be a whole number")
    if value < minimum:
        frappe.throw(f"{field} must be at least {minimum}")
    if value > maximum:
        frappe.throw(f"{field} must be at most {maximum}")
    return value


def _to_bool(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
    frappe.throw(f"{field} must be true or false")


def _to_money(value, field, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        frappe.throw(f"{field} must be a number")
    text = str(value).strip()
    if not text or len(text) > 40 or "_" in text:
        frappe.throw(f"{field} must be a number")
    try:
        number = Decimal(text)
    except InvalidOperation:
        frappe.throw(f"{field} must be a number")
    if not number.is_finite():
        frappe.throw(f"{field} must be a finite number")
    if number < 0:
        frappe.throw(f"{field} cannot be negative")
    if number > MAX_PRICE:
        frappe.throw(f"{field} cannot be more than {MAX_PRICE}")
    if number != number.quantize(_MONEY_QUANT):
        frappe.throw(f"{field} can have at most {PRICE_DECIMAL_PLACES} decimal places")
    if number.is_zero():
        if not allow_zero:
            frappe.throw(f"{field} must be greater than 0")
        return Decimal("0.00")  # avoids "-0"
    return number.quantize(_MONEY_QUANT)


def _choice(value, field, allowed):
    value = _clean_str(value, field, min_len=1)
    if value not in allowed:
        frappe.throw(f"{field} must be one of: {', '.join(allowed)}")
    return value


def normalize_plan_name(value, field="plan_name"):
    """trim + collapse inner whitespace, so 'Gold  Plan ' == 'Gold Plan'."""
    value = _clean_str(value, field, 1, MAX_NAME_LENGTH)
    return " ".join(value.split())


def _plan_code(value):
    if value is None:
        return None
    value = _clean_str(value, "plan_code", max_len=MAX_PLAN_CODE_LENGTH).upper()
    if not value:
        return None
    if not _PLAN_CODE_RE.match(value):
        frappe.throw("plan_code may contain only letters, numbers, '-' and '_'")
    return value


def _parse_modules(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            frappe.throw("modules must be a valid JSON list")
    if not isinstance(value, list):
        frappe.throw("modules must be a list")
    if not value:
        frappe.throw("modules must contain at least 1 item")
    if len(value) > MAX_MODULES_PER_PLAN:
        frappe.throw(f"modules can contain at most {MAX_MODULES_PER_PLAN} items")

    cleaned, seen, duplicates = [], set(), set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            frappe.throw(f"modules[{index}] must be an object")
        if item.get("module") is None:
            frappe.throw(f"modules[{index}].module is required")
        name = _clean_str(item["module"], f"modules[{index}].module", 1, MAX_NAME_LENGTH)
        if name in seen:
            duplicates.add(name)
        seen.add(name)
        price = None
        if item.get("price") is not None:
            price = _to_money(item["price"], f"modules[{index}].price", allow_zero=True)
        cleaned.append({"module": name, "price": price})

    if duplicates:
        frappe.throw(f"Duplicate modules selected: {', '.join(sorted(duplicates))}")
    return cleaned


def _opt_str(params, key, max_len=None):
    value = _blank_to_none(params.get(key))
    return None if value is None else _clean_str(value, key, 0, max_len)


def _opt_choice(params, key, allowed):
    value = _blank_to_none(params.get(key))
    return None if value is None else _choice(value, key, allowed)


def _opt_int(params, key, default, minimum, maximum):
    value = _blank_to_none(params.get(key))
    return default if value is None else _to_int(value, key, minimum, maximum)


_FIELD_RULES = {
    "plan_name": normalize_plan_name,
    "plan_code": _plan_code,
    "user_limit": lambda v: _to_int(v, "user_limit", 0, MAX_USER_LIMIT),  
    "description": lambda v: None if v is None else _clean_str(v, "description", 0, MAX_DESCRIPTION_LENGTH),
    "modules": _parse_modules,
    "billing_frequency": lambda v: _choice(v, "billing_frequency", BILLING_FREQUENCIES),
    "pricing_model": lambda v: _choice(v, "pricing_model", PRICING_MODELS),
    "currency": lambda v: _clean_str(v, "currency", 1, MAX_NAME_LENGTH),
    "base_price": lambda v: _to_money(v, "base_price"), 
    "setup_fee": lambda v: _to_money(v, "setup_fee", allow_zero=True),
    "trial_enabled": lambda v: _to_bool(v, "trial_enabled"),
    "trial_days": lambda v: _to_int(v, "trial_days", 0, MAX_TRIAL_DAYS),
    "renewal_mode": lambda v: _choice(v, "renewal_mode", RENEWAL_MODES),
    "billing_cycles": lambda v: _to_int(v, "billing_cycles", 0, MAX_BILLING_CYCLES),
}

# `status` is deliberately NOT accepted on create: create always makes a Draft.
_CREATE_REQUIRED = {"plan_name", "currency", "modules", "pricing_model", "billing_frequency"}
_NULLABLE = {"plan_code", "description"}
_CREATE_DEFAULTS = {
    "plan_code": None,
    "user_limit": 0,  
    "description": None,
    "base_price": None,  
    "setup_fee": Decimal("0.00"),
    "trial_enabled": False,
    "trial_days": 0,
    "renewal_mode": RENEWAL_AUTO,
    "billing_cycles": 0,
}


def assert_trial_and_renewal_rules(trial_enabled, trial_days, renewal_mode, billing_cycles):
    if trial_enabled and trial_days < 1:
        frappe.throw("trial_days must be at least 1 when free trial is enabled")
    if renewal_mode == RENEWAL_FIXED and billing_cycles < 1:
        frappe.throw("billing_cycles must be at least 1 for Fixed cycles")


def assert_module_prices(modules):
    for index, module in enumerate(modules, start=1):
        price = module.get("price")
        if price is None or price <= 0:
            frappe.throw(f"modules[{index}].price must be greater than 0 for Per Module pricing")


def validate_create_payload(payload: dict) -> dict:
    payload = payload or {}
    data = {}
    for field, rule in _FIELD_RULES.items():
        if field in payload:
            value = payload[field]
            if value is None and field not in _NULLABLE:
                frappe.throw(f"{field} cannot be null")
            data[field] = rule(value)
        elif field in _CREATE_REQUIRED:
            frappe.throw(f"{field} is required")
        else:
            data[field] = _CREATE_DEFAULTS[field]

    data["status"] = DEFAULT_STATUS  # payload status (if any) is ignored on purpose

    assert_trial_and_renewal_rules(
        data["trial_enabled"], data["trial_days"], data["renewal_mode"], data["billing_cycles"]
    )
    if data["pricing_model"] == PRICING_FLAT:
        if data["base_price"] is None:
            frappe.throw("base_price is required for Flat pricing")
    else:
        assert_module_prices(data["modules"])
    return data


def validate_update_payload(payload: dict) -> dict:
    payload = payload or {}
    if payload.get("id") is None:
        frappe.throw("id is required")
    result = {"id": _clean_str(payload["id"], "id", 1, MAX_NAME_LENGTH)}

    modified = _blank_to_none(payload.get("modified"))
    if modified is not None:
        result["modified"] = _clean_str(modified, "modified")

    if "status" in payload:
        frappe.throw("status cannot be changed here, use the update_status API")

    for field, rule in _FIELD_RULES.items():
        if field not in payload:
            continue
        value = payload[field]
        if value is None and field != "description":
            frappe.throw(f"{field} cannot be null")
        result[field] = rule(value)

    if "plan_code" in result and result["plan_code"] is None:
        frappe.throw("plan_code cannot be blank")
    return result


def validate_status_payload(payload: dict) -> dict:
    payload = payload or {}
    if payload.get("id") is None:
        frappe.throw("id is required")
    if payload.get("status") is None:
        frappe.throw("status is required")

    result = {
        "id": _clean_str(payload["id"], "id", 1, MAX_NAME_LENGTH),
        "status": _choice(payload["status"], "status", PLAN_STATUSES),
        "modified": None,
    }
    modified = _blank_to_none(payload.get("modified"))
    if modified is not None:
        result["modified"] = _clean_str(modified, "modified")
    return result


def validate_get_by_id_params(params: dict) -> dict:
    params = params or {}
    if _blank_to_none(params.get("id")) is None:
        frappe.throw("id is required")
    return {"id": _clean_str(params["id"], "id", 1, MAX_NAME_LENGTH)}


def validate_list_params(params: dict) -> dict:
    params = params or {}

    sort_by = _opt_str(params, "sort_by") or DEFAULT_SORT_BY
    if sort_by not in ALLOWED_SORT_FIELDS:
        frappe.throw(f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORT_FIELDS))}")

    sort_order = (_opt_str(params, "sort_order") or DEFAULT_SORT_ORDER).lower()
    if sort_order not in SORT_ORDERS:
        frappe.throw(f"sort_order must be one of: {', '.join(SORT_ORDERS)}")

    return {
        "page": _opt_int(params, "page", DEFAULT_PAGE, 1, MAX_PAGE),
        "page_size": _opt_int(params, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE),
        "search": _opt_str(params, "search", MAX_NAME_LENGTH),
        "status": _opt_choice(params, "status", PLAN_STATUSES),
        "pricing_model": _opt_choice(params, "pricing_model", PRICING_MODELS),
        "billing_frequency": _opt_choice(params, "billing_frequency", BILLING_FREQUENCIES),
        "product": _opt_str(params, "product", MAX_NAME_LENGTH),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


def assert_price_precision() -> None:
    """The price precision is not forced to 2 on the fields (schema is unchanged).
    If the field precision / System Settings currency precision is KNOWN and below 2, Frappe
    would silently round 10.55 to 11 on save -> refuse (500 + log) instead of mis-billing."""
    field = frappe.get_meta(PLAN_DOCTYPE).get_field("base_price")
    precision = (field.precision if field else None) or frappe.get_system_settings("currency_precision")
    if precision in (None, ""):
        # same fallback Frappe uses: decimals of the global Number Format (default "#,###.##")
        number_format = frappe.get_system_settings("number_format") or "#,###.##"
        precision = get_number_format_info(number_format)[2]
    if int(precision) < PRICE_DECIMAL_PLACES:
        raise RuntimeError(
            f"Currency precision is {precision} but plans need {PRICE_DECIMAL_PLACES} decimals; "
            "set System Settings > Currency Precision to 2 or more"
        )


def get_locked_plan(plan_id: str):
    try:
        return frappe.get_doc(PLAN_DOCTYPE, plan_id, for_update=True)
    except frappe.DoesNotExistError:
        frappe.throw(MSG_PLAN_NOT_FOUND.format(plan_id=plan_id), frappe.DoesNotExistError)


def assert_not_stale(doc, expected_modified) -> None:
    if not expected_modified:
        return
    try:
        expected = get_datetime(expected_modified)
    except Exception:
        frappe.throw("modified is not a valid datetime")
    if expected != get_datetime(doc.modified):
        frappe.throw(MSG_STALE, ConflictError)


def save_doc(doc) -> None:
    try:
        doc.save(ignore_permissions=True)
    except frappe.TimestampMismatchError:
        frappe.throw(MSG_STALE, ConflictError)


def split_products(value):
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def to_db_value(value):
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, Decimal):
        return float(value) 
    return value