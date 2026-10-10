import frappe
from frappe.utils import getdate
from rolaface_subscription.modules.subscription.constant import (
    LIVE_STATUSES,
    STATUS_CANCELLED,
    SUBSCRIPTION_DOCTYPE,
)
from rolaface_subscription.modules.subscription.utils import derive_status

def refresh_subscription_statuses() -> int:
    """Daily: move submitted subscriptions along their dates (Scheduled -> Trialing -> Active -> Expired,
    and Cancelled once a scheduled cancel date is reached). Drafts are never touched.
    Returns how many subscriptions changed."""
    today = getdate()
    rows = frappe.get_all(
        SUBSCRIPTION_DOCTYPE,
        filters={"docstatus": 1, "status": ["in", LIVE_STATUSES]},
        fields=["name", "status", "start_date", "trial_end_date", "end_date", "cancelled_on"],
        limit_page_length=0,
    )

    changed = 0
    for row in rows:
        new_status = derive_status(row, today)
        if new_status == row.status:
            continue
        if new_status == STATUS_CANCELLED:
            changed += _cancel(row)
        else:
            changed += _set_submitted_status(row, new_status)
    return changed


def _set_submitted_status(row, new_status) -> int:
    """Save the new status the normal way, so it is synced to the customer site (on_update_after_submit).
    If that fails, the change is rolled back and retried on the next run."""
    try:
        doc = frappe.get_doc(SUBSCRIPTION_DOCTYPE, row.name, for_update=True)
        if doc.docstatus != 1 or doc.status != row.status:
            return 0
        doc.status = new_status
        doc.flags.ignore_permissions = True
        doc.save()
        frappe.db.commit()
        return 1
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Status update failed for subscription {row.name}")
        return 0


def _cancel(row) -> int:
    """A scheduled cancel date was reached: cancel the document the Frappe way (docstatus 2).
    One failing subscription must not stop the others, so errors are logged and skipped."""
    try:
        doc = frappe.get_doc(SUBSCRIPTION_DOCTYPE, row.name, for_update=True)
        if doc.docstatus != 1 or doc.status != row.status:
            return 0  # changed by someone else in the meantime
        doc.flags.ignore_permissions = True
        doc.cancel()
        frappe.db.commit()
        return 1
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Scheduled cancel failed for subscription {row.name}")
        return 0
