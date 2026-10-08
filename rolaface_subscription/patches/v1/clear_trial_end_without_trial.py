import frappe

def execute():
    for name in frappe.get_all(
        "Custom Subscription", filters={"trial_enabled": 0, "trial_end_date": ["is", "set"]}, pluck="name"
    ):
        frappe.db.set_value("Custom Subscription", name, "trial_end_date", None, update_modified=False)
