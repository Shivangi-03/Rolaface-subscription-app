import hashlib
import re
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import frappe
from frappe.utils import add_months, cint, get_datetime, getdate , add_days

from rolaface_subscription.modules.plan.constant import MAX_NAME_LENGTH, RENEWAL_FIXED
from rolaface_subscription.modules.plan.utils import (
    _blank_to_none,
    _choice,
    _clean_str,
    _opt_int,
    _opt_str,
    _to_bool,
    _to_int,
    _to_money,
)
from rolaface_subscription.modules.subscription.constant import (
    ALL_STATUSES,
    ALLOWED_SORT_FIELDS,
    BILLING_CUSTOM,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    MAX_CUSTOM_MONTHS,
    MAX_NOTES_LENGTH,
    MAX_PAGE,
    MAX_PAGE_SIZE,
    MAX_REASON_LENGTH,
    MSG_NOT_FOUND,
    MSG_STALE,
    SORT_ORDERS,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_SCHEDULED,
    STATUS_TRIALING,
    SUBSCRIPTION_DOCTYPE,
    SUBSCRIPTION_FREQUENCIES,
)
from rolaface_subscription.utils.api_response import ConflictError

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CENT = Decimal("0.01")


def _to_date(value, field) -> date:
    if not isinstance(value, str) or not _DATE_RE.match(value.strip()):
        frappe.throw(f"{field} must be a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        frappe.throw(f"{field} is not a valid date")


def money(value) -> Decimal:
    """DB / float value -> Decimal with exactly 2 decimals"""
    return Decimal(str(value or 0)).quantize(CENT)


def period_bounds(anchor: date, months: int, cycle_no: int):
    return add_months(anchor, (cycle_no - 1) * months), add_months(anchor, cycle_no * months)


def _d(value):
    return getdate(value) if value else None


def derive_status(row, today: date) -> str:

    cancelled_on, end_date = _d(row.cancelled_on), _d(row.end_date)
    if cancelled_on and cancelled_on <= today:
        return STATUS_CANCELLED
    if end_date and end_date <= today:
        return STATUS_EXPIRED
    if _d(row.start_date) > today:
        return STATUS_SCHEDULED
    if _d(row.trial_end_date) > today:
        return STATUS_TRIALING
    return STATUS_ACTIVE


def current_period(row, today: date):
    anchor = _d(row.trial_end_date)
    months = max(cint(row.period_months), 1)
    end_date = _d(row.end_date)
    ref = min(today, add_days(end_date, -1)) if end_date else today  

    n = 1
    elapsed = (ref.year - anchor.year) * 12 + (ref.month - anchor.month)
    if elapsed > 0:
        n = max(1, elapsed // months)
    while add_months(anchor, n * months) <= ref:
        n += 1
    while n > 1 and add_months(anchor, (n - 1) * months) > ref:
        n -= 1
    start, end = period_bounds(anchor, months, n)
    if end_date and end > end_date:
        end = end_date
    return start, end



def build_state(row, today):
    status = derive_status(row, today)
    start, end = current_period(row, today)
    cancelled_on = _d(row.cancelled_on)
    expiry = _d(row.end_date) or end
    if cancelled_on and cancelled_on < expiry:
        expiry = cancelled_on
    return {
        "status": status,
        "current_period_start": start,
        "current_period_end": end,
         "expiry_date": expiry,
        "cancel_scheduled": bool(cancelled_on and cancelled_on > today),
    }


_NOT_CANCELLED = "(cancelled_on IS NULL OR cancelled_on > %(today)s)"
STATUS_SQL = {
    STATUS_CANCELLED: "(cancelled_on IS NOT NULL AND cancelled_on <= %(today)s)",
    STATUS_EXPIRED: f"({_NOT_CANCELLED} AND end_date IS NOT NULL AND end_date <= %(today)s)",
    STATUS_SCHEDULED: f"({_NOT_CANCELLED} AND start_date > %(today)s)",
    STATUS_TRIALING: f"({_NOT_CANCELLED} AND start_date <= %(today)s AND trial_end_date > %(today)s)",
    STATUS_ACTIVE: (
        f"({_NOT_CANCELLED} AND trial_end_date <= %(today)s "
        "AND (end_date IS NULL OR end_date > %(today)s))"
    ),
}
LIVE_SQL = f"({_NOT_CANCELLED} AND (end_date IS NULL OR end_date > %(today)s))"
ACCESS_SQL = f"({LIVE_SQL} AND start_date <= %(today)s)"


@contextmanager
def named_lock(key_text: str, wait_seconds: int = 10):
    """MariaDB named lock: requests with the same key run one after the other.
    Commit right after taking it (nothing is pending yet) so the next read sees a fresh snapshot,
    and commit again before releasing so the next holder can see what we wrote."""
    key = "sub:" + hashlib.md5(key_text.casefold().encode()).hexdigest()
    if frappe.db.sql("SELECT GET_LOCK(%s, %s)", (key, wait_seconds))[0][0] != 1:
        frappe.throw("Another request is working on this subscription, please retry", ConflictError)
    try:
        frappe.db.commit()
        yield
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()  
        raise
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", (key,))


def validate_create_payload(payload: dict) -> dict:
    payload = payload or {}
    for field in ("customer", "plan", "start_date","end_date"):
        if _blank_to_none(payload.get(field)) is None:
            frappe.throw(f"{field} is required")

    data = {
        "customer": _clean_str(payload["customer"], "customer", 1, MAX_NAME_LENGTH),
        "plan": _clean_str(payload["plan"], "plan", 1, MAX_NAME_LENGTH),
        "start_date": _to_date(payload["start_date"], "start_date"),
        "end_date": _to_date(payload["end_date"], "end_date"),
    }

    frequency = _blank_to_none(payload.get("billing_frequency"))
    data["billing_frequency"] = (
        None if frequency is None else _choice(frequency, "billing_frequency", SUBSCRIPTION_FREQUENCIES)
    )
    months = _blank_to_none(payload.get("custom_interval_months"))
    if months in (0, "0"):  # a client echoing back what GET returned
        months = None
    if data["billing_frequency"] == BILLING_CUSTOM:
        if months is None:
            frappe.throw("custom_interval_months is required when billing_frequency is Custom")
        data["custom_interval_months"] = _to_int(months, "custom_interval_months", 1, MAX_CUSTOM_MONTHS)
    else:
        if months is not None:
            frappe.throw("custom_interval_months can only be sent when billing_frequency is Custom")
        data["custom_interval_months"] = None

    discount = _blank_to_none(payload.get("discount_amount"))
    data["discount_amount"] = (
        Decimal("0.00") if discount is None else _to_money(discount, "discount_amount", allow_zero=True)
    )
    data["notes"] = _opt_str(payload, "notes", MAX_NOTES_LENGTH)
    return data


def validate_update_payload(payload: dict) -> dict:
    payload = payload or {}
    if _blank_to_none(payload.get("id")) is None:
        frappe.throw("id is required")
    result = {"id": _clean_str(payload["id"], "id", 1, MAX_NAME_LENGTH)}

    modified = _blank_to_none(payload.get("modified"))
    if modified is not None:
        result["modified"] = _clean_str(modified, "modified")

    if "discount_amount" in payload:
        if payload["discount_amount"] is None:
            frappe.throw("discount_amount cannot be null")
        result["discount_amount"] = _to_money(payload["discount_amount"], "discount_amount", allow_zero=True)
    if "notes" in payload:
        value = _blank_to_none(payload["notes"])
        result["notes"] = None if value is None else _clean_str(value, "notes", 0, MAX_NOTES_LENGTH)
    if not any(k in result for k in ("discount_amount", "notes")):
        frappe.throw("Nothing to update, send discount_amount or notes")
    return result


def validate_cancel_payload(payload: dict) -> dict:
    payload = payload or {}
    if _blank_to_none(payload.get("id")) is None:
        frappe.throw("id is required")
    if _blank_to_none(payload.get("reason")) is None:
        frappe.throw("reason is required")
    if _blank_to_none(payload.get("immediate")) is None:
        frappe.throw("immediate is required (true = cancel now, false = cancel at period end)")
    result = {
        "id": _clean_str(payload["id"], "id", 1, MAX_NAME_LENGTH),
        "reason": _clean_str(payload["reason"], "reason", 1, MAX_REASON_LENGTH),
        "immediate": _to_bool(payload["immediate"], "immediate"),
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


def validate_entitlement_params(params: dict) -> dict:
    params = params or {}
    if _blank_to_none(params.get("customer")) is None:
        frappe.throw("customer is required")
    return {"customer": _clean_str(params["customer"], "customer", 1, MAX_NAME_LENGTH)}


def validate_my_subscription_params(params: dict) -> dict:
    params = params or {}
    if _blank_to_none(params.get("customer")) is None:
        frappe.throw("customer is required")
    return {"customer": _clean_str(params["customer"], "customer", 1, MAX_NAME_LENGTH)}


def validate_available_plans_params(params: dict) -> dict:
    params = params or {}
    return {
        "customer": _opt_str(params, "customer", MAX_NAME_LENGTH),
        "page": _opt_int(params, "page", DEFAULT_PAGE, 1, MAX_PAGE),
        "page_size": _opt_int(params, "page_size", 50, 1, MAX_PAGE_SIZE),
    }


def validate_list_params(params: dict) -> dict:
    params = params or {}
    sort_by = _opt_str(params, "sort_by") or DEFAULT_SORT_BY
    if sort_by not in ALLOWED_SORT_FIELDS:
        frappe.throw(f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORT_FIELDS))}")
    sort_order = (_opt_str(params, "sort_order") or DEFAULT_SORT_ORDER).lower()
    if sort_order not in SORT_ORDERS:
        frappe.throw(f"sort_order must be one of: {', '.join(SORT_ORDERS)}")
    status = _opt_str(params, "status")
    if status is not None and status not in ALL_STATUSES:
        frappe.throw(f"status must be one of: {', '.join(ALL_STATUSES)}")
    return {
        "page": _opt_int(params, "page", DEFAULT_PAGE, 1, MAX_PAGE),
        "page_size": _opt_int(params, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE),
        "search": _opt_str(params, "search", MAX_NAME_LENGTH),
        "status": status,
        "customer": _opt_str(params, "customer", MAX_NAME_LENGTH),
        "plan": _opt_str(params, "plan", MAX_NAME_LENGTH),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


def get_locked_subscription(sub_id: str):
    try:
        return frappe.get_doc(SUBSCRIPTION_DOCTYPE, sub_id, for_update=True)
    except frappe.DoesNotExistError:
        frappe.throw(MSG_NOT_FOUND.format(sub_id=sub_id), frappe.DoesNotExistError)


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