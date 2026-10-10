import frappe
from .utils import make_code

# Product code -> module names. Depends on seed_products having run first.
MODULES = {
	"ERP": [
		"Sales",
		"Customer",
		"Procurement",
		"Inventory",
		"Accounting",
		"Assets",
	],
	"LMS": [
		"Customer",
		"Collateral",
		"Lending Setup",
		"Lending Operations",
		"Accounting",
		"Lending Reports",
	],
	"LOS": [
		"Customer",
		"Collateral",
		"Origination Setup",
		"Origination",
		"Accounting",
	],
	"HRMS": [
		"Employee Management",
		"Leave Management",
		"Timesheet and Attendance",
		"Payroll",
		"HR Setup",
	],
}

def seed_modules():
	"""Create default Custom Module records per product that don't exist yet."""
	for product, module_names in MODULES.items():
		for module_name in module_names:
			module_code = make_code(module_name)

			if frappe.db.exists("Custom Module", {"product": product, "module_code": module_code}):
				continue

			frappe.get_doc(
				{
					"doctype": "Custom Module",
					"product": product,
					"module_code": module_code,
					"module_name": module_name,
					"is_active": 1,
				}
			).insert(ignore_permissions=True)
