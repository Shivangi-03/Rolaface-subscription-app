import json
import frappe
import requests
from frappe.utils import getdate

from rolaface_subscription.modules.subscription.constant import (
    CUSTOMER_BACKEND_URL_FIELD,
    CUSTOMER_DOCTYPE,
    CUSTOMER_SYNC_CREATE_PATH,
    CUSTOMER_SYNC_DELETE_PATH,
)
from rolaface_subscription.modules.subscription.utils import build_state
from rolaface_subscription.utils.api_response import CustomerSyncError


def _get_connection(customer: str) -> dict:
    url = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, CUSTOMER_BACKEND_URL_FIELD)
    if not url or not url.strip():
        frappe.throw(f"Customer '{customer}' has no backend URL, cannot sync the subscription", CustomerSyncError)

    # TODO: add master -> customer site authentication (planned separately)
    return {
        "base_url": url.strip().rstrip("/"),
        "headers": {"Content-Type": "application/json", "Accept": "application/json"},
    }


def _remote_message(res) -> str:
    """Pull a readable message out of a customer site response (auth_api or Frappe error format)."""
    try:
        body = res.json()
    except ValueError:
        return (res.text or "").strip()[:300] or f"HTTP {res.status_code}"

    msg = body.get("message")
    if isinstance(msg, dict):
        msg = msg.get("message")
    if not msg and body.get("_server_messages"):
        try:
            msg = json.loads(json.loads(body["_server_messages"])[0]).get("message")
        except (ValueError, IndexError, TypeError, AttributeError):
            pass
    return str(msg or body.get("exc_type") or f"HTTP {res.status_code}")


def _remote_succeeded(res) -> bool:
    if not res.ok:
        return False
    try:
        body = res.json()
    except ValueError:
        return False
    msg = body.get("message")
    return isinstance(msg, dict) and msg.get("status") == "success"


def build_sync_payload(doc) -> dict:
    return {
        "masterSubscriptionName": doc.name,
        "subscriptionStatus": build_state(doc, getdate())["status"],
        # the whole subscription (with module rows) is stored in the customer's JSON field
        "details": json.loads(frappe.as_json(doc.as_dict(convert_dates_to_str=True))),
    }


def sync_subscription_to_customer(doc) -> dict:
    conn = _get_connection(doc.customer)
    payload = build_sync_payload(doc)
    try:
        res = requests.post(
            conn["base_url"] + CUSTOMER_SYNC_CREATE_PATH,
            data=frappe.as_json(payload),
            headers=conn["headers"]
        )
    except requests.RequestException as e:
        delete_subscription_from_customer(conn, doc.name)
        frappe.throw(f"Could not reach the customer site to sync the subscription: {type(e).__name__}",
                     CustomerSyncError)

    if not _remote_succeeded(res):
        if res.status_code >= 500:
            delete_subscription_from_customer(conn, doc.name)
        frappe.throw(f"Customer site rejected the subscription sync: {_remote_message(res)}", CustomerSyncError)

    return conn

def delete_subscription_from_customer(conn: dict, name: str) -> bool:
    try:
        res = requests.delete(
            conn["base_url"] + CUSTOMER_SYNC_DELETE_PATH,
            data=frappe.as_json({"masterSubscriptionName": name}),
            headers=conn["headers"],
        )
        if _remote_succeeded(res) or res.status_code == 404:
            return True
        reason = _remote_message(res)
    except requests.RequestException as e:
        reason = f"{type(e).__name__}: {e}"

    frappe.log_error(
        title="Customer subscription sync rollback failed",
        message=f"Subscription '{name}' may still exist on {conn['base_url']}, remove it manually.\n{reason}",
    )
    return False
