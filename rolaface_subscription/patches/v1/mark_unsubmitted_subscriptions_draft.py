import frappe

from rolaface_subscription.modules.subscription.constant import STATUS_DRAFT, SUBSCRIPTION_DOCTYPE


def execute():
    """Unsubmitted subscriptions created before the Draft status existed got a live status: make them Draft."""
    for name in frappe.get_all(
        SUBSCRIPTION_DOCTYPE, filters={"docstatus": 0, "status": ["!=", STATUS_DRAFT]}, pluck="name"
    ):
        frappe.db.set_value(SUBSCRIPTION_DOCTYPE, name, "status", STATUS_DRAFT, update_modified=False)
