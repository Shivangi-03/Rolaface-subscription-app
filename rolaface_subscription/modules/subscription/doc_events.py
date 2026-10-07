import frappe
from frappe.utils import cint, getdate
from rolaface_subscription.modules.subscription.constant import (
    LIVE_STATUSES,
    STATUS_CANCELLED,
    SUBSCRIPTION_DOCTYPE,
)
from rolaface_subscription.modules.subscription.sync import (
    delete_subscription_from_customer,
    sync_subscription_to_customer,
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
