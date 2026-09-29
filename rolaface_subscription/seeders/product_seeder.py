import frappe

PRODUCTS = [
	{"product_code": "ERP", "product_name": "ERP"},
	{"product_code": "LMS", "product_name": "LMS"},
	{"product_code": "LOS", "product_name": "LOS"},
	{"product_code": "HRMS", "product_name": "HRMS"},
]

def seed_products():
	"""Create default Custom Product records that don't exist yet."""
	for product in PRODUCTS:
		if frappe.db.exists("Custom Product", product["product_code"]):
			continue

		frappe.get_doc({"doctype": "Custom Product", "is_active": 1, **product}).insert(
			ignore_permissions=True
		)
