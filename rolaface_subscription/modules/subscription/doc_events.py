import frappe
from frappe.utils import cint, getdate
from rolaface_subscription.modules.subscription.constant import (
    LIVE_STATUSES,
    STATUS_CANCELLED,
    SUBSCRIPTION_DOCTYPE,
)
from rolaface_subscription.modules.subscription.sync import (
    get_connection,
    build_sync_payload,
    delete_subscription_from_customer,
    restore_subscription_on_customer,
    sync_subscription_to_customer,
    update_subscription_on_customer,
)
from rolaface_subscription.modules.subscription.utils import derive_status
from rolaface_subscription.utils.api_response import ConflictError

def before_submit(doc) -> None:
    if frappe.db.exists(
        SUBSCRIPTION_DOCTYPE,
        {"customer": doc.customer, "plan": doc.plan, "status": ["in", LIVE_STATUSES], "name": ["!=", doc.name]},
    ):
        frappe.throw("This customer already has a live subscription for this plan", ConflictError)
    doc.status = derive_status(doc, getdate())

def on_submit(doc) -> None:
    if not cint(doc.auto_sync):
        return
    conn = sync_subscription_to_customer(doc)
    # if anything after this fails (incl. the commit), the transaction is rolled back:
    # remove the copy on the customer site too
    frappe.db.after_rollback.add(lambda: delete_subscription_from_customer(conn, doc.name))

def before_cancel(doc) -> None:
    today = getdate()
    if not doc.cancelled_on or getdate(doc.cancelled_on) > today:
        doc.cancelled_on = today
    doc.status = STATUS_CANCELLED


def on_update_after_submit(doc) -> None:
    sync_update(doc)


def on_cancel(doc) -> None:
    sync_update(doc)


def sync_update(doc, previous=None) -> None:
    """After submit, every change is pushed to the customer site in the same transaction.
    If the push or anything after it fails, the master change is rolled back and the
    customer site gets its previous state back."""
    if not cint(doc.auto_sync):
        return
    previous = previous or doc.get_doc_before_save()
    conn = get_connection(doc.customer)
    if previous is not None:
        old_payload = build_sync_payload(previous)
        # registered before the call: a timeout may still have applied the update remotely
        frappe.db.after_rollback.add(lambda: restore_subscription_on_customer(conn, old_payload))
    update_subscription_on_customer(doc, conn)
