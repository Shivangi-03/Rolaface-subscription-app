# Copyright (c) 2026, Rolaface and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CustomModule(Document):
	def autoname(self):
		# e.g. product "ERP" + module_code "SALES" -> "ERP-SALES"
		self.module_code = (self.module_code or "").strip().upper()
		if not self.module_code:
			frappe.throw(_("Module Code is required"))

		self.name = f"{self.product}-{self.module_code}"
