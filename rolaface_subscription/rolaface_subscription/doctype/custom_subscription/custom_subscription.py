# Copyright (c) 2026, Rolaface and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from rolaface_subscription.modules.subscription.constant import MAX_CUSTOM_MONTHS
from rolaface_subscription.modules.subscription import doc_events


class CustomSubscription(Document):

    def before_insert(self):
        if not self.flags.get("via_service"):
            frappe.throw(_("Subscriptions can only be created through the subscription API"))

    def validate(self):
        subtotal, discount = flt(self.subtotal, 2), flt(self.discount_amount, 2)
        if subtotal <= 0:
            frappe.throw(_("Subtotal must be greater than 0"))
        if discount < 0 or discount > subtotal:
            frappe.throw(_("Discount cannot be negative or more than the subtotal"))
        self.grand_total = flt(subtotal - discount, 2)

        if self.billing_frequency == "Custom":
            if not 1 <= (self.custom_interval_months or 0) <= MAX_CUSTOM_MONTHS:
                frappe.throw(_("Custom interval must be between 1 and {0} months").format(MAX_CUSTOM_MONTHS))
        if (self.period_months or 0) < 1:
            frappe.throw(_("Billing period must be at least 1 month"))

        start, trial_end = getdate(self.start_date), getdate(self.trial_end_date)
        if trial_end < start:
            frappe.throw(_("Trial end date cannot be before the start date"))
        if self.is_new() and not self.end_date:
            frappe.throw(_("End date is required"))
        if self.end_date and getdate(self.end_date) <= trial_end:
            frappe.throw(_("End date must be after the trial end date"))

        seen = set()
        for row in self.get("modules") or []:
            if row.module in seen:
                frappe.throw(_("Row {0}: module {1} is added more than once").format(row.idx, row.module))
            seen.add(row.module)

    def before_submit(self):
        doc_events.before_submit(self)

    def on_submit(self):
        doc_events.on_submit(self)

    def before_cancel(self):
        doc_events.before_cancel(self)

    # def on_trash(self):
    #     frappe.throw(_("Subscriptions cannot be deleted. Cancel the subscription instead."))