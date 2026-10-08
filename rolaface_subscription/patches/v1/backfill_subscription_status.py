import frappe
from frappe.utils import getdate

from rolaface_subscription.modules.subscription.constant import (
    STATUS_CANCELLED,
    STATUS_DRAFT,
    SUBSCRIPTION_DOCTYPE,
)
from rolaface_subscription.modules.subscription.utils import derive_status


def execute():
    """Fill in `status` for subscriptions created before the field existed."""
    today = getdate()
    for row in frappe.get_all(
        SUBSCRIPTION_DOCTYPE,
        filters={"status": ["is", "not set"]},
        fields=["name", "docstatus", "start_date", "trial_end_date", "end_date", "cancelled_on"],
    ):
        if row.docstatus == 0:
            status = STATUS_DRAFT
        elif row.docstatus == 2:
            status = STATUS_CANCELLED
        else:
            # leave a reached cancel date to the daily job, so it is cancelled the Frappe way (docstatus 2)
            status = derive_status(frappe._dict(row, cancelled_on=None), today)
        frappe.db.set_value(SUBSCRIPTION_DOCTYPE, row.name, "status", status, update_modified=False)
