import frappe
from frappe.utils import getdate
from rolaface_subscription.modules.subscription.constant import (
    LIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_DRAFT,
    SUBSCRIPTION_DOCTYPE,
)
from rolaface_subscription.modules.subscription.utils import derive_status

def refresh_subscription_statuses() -> int:
    """Daily: move stored statuses along their dates (Scheduled -> Trialing -> Active -> Expired, and
    Cancelled once a scheduled cancel date is reached). Rows without a status are filled in too;
    unsubmitted subscriptions are always Draft.
    Returns how many subscriptions changed."""
    today = getdate()
    rows = frappe.get_all(
        SUBSCRIPTION_DOCTYPE,
        or_filters=[["status", "in", LIVE_STATUSES], ["status", "is", "not set"]],
        fields=["name", "docstatus", "status", "start_date", "trial_end_date", "end_date", "cancelled_on"],
        limit_page_length=0,
    )

    changed = 0
    for row in rows:
        new_status = derive_status(row, today) if row.docstatus == 1 else STATUS_DRAFT
        if new_status == row.status:
            continue
        if new_status == STATUS_CANCELLED:
            changed += _cancel(row)
            continue
        # only if nobody changed the status in the meantime (e.g. an immediate cancel)
        frappe.db.set_value(
            SUBSCRIPTION_DOCTYPE,
            {"name": row.name, "status": row.status or ["is", "not set"]},
            "status",
            new_status,
        )
        changed += 1
    frappe.db.commit()
    return changed


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
