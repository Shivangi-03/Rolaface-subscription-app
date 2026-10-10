import frappe
from .utils import make_code

# Product code -> module name -> sub-module names. Depends on seed_modules having run first.
SUB_MODULES = {
	"ERP": {
		"Sales": [
			"Sales Order",
			"Quotations",
			"Proforma Invoice",
			"Invoices",
			"Credit Notes",
			"Sales Debit Notes",
			"Reports",
			"Sales Analytics",
			"PDC",
		],
		"Customer": [
			"Customer",
			"Customer Payment",
			"Customer Group",
			"Reports",
		],
		"Procurement": [
			"Supplier",
			"Supplier Payment",
			"RFQs",
			"Purchase Orders",
			"Purchase Invoice",
			"Import PI",
			"Debit Notes",
			"Purchase Analytics",
			"PI BarCode",
		],
		"Inventory": [
			"Items",
			"Imported Items",
			"Item Group",
			"Warehouse",
			"Stock",
		],
		"Accounting": [
			"General Ledger",
			"Trial Balance",
			"Receivables",
			"Payables",
			"Profit & Loss",
			"Balance Sheet",
			"Cash Flow",
		],
		"Assets": [
			"Asset Category",
			"Asset",
			"Asset Movement",
		],
		"Human Resources": [
			"Employee Management",
			"Leave Management",
			"Timesheet & Attendance",
			"Performance & Growth",
			"Payroll",
			"HR Setup",
		],
		"Expense Management": [
			"Expense Type",
			"Expense Claim",
			"Employee Advance",
			"Expense Payment",
		],
	},
	"LMS": {
		"Customer": [
			"Customer",
		],
		"Collateral": [
			"Collateral Type",
			"Collateral",
		],
		"Lending Setup": [
			"Loan Category",
			"Loan Classification",
			"Collection Sequence",
			"Fee and Charges",
			"Loan Product",
			"Contract Templates",
			"Map Loan Products",
			"Lending Configuration",
		],
		"Lending Operations": [
			"Loan Booking",
			"Loan Disbursement",
			"Loan Repayment",
			"Loan Waiver",
			"Loan Capitalization",
			"Loan Restructure",
			"Loan Write-Off",
			"Loan Transfer",
		],
		"Accounting": [
			"General Ledger",
			"Trial Balance",
			"Receivable",
			"Payable",
			"Profit & Loss",
			"Balance Sheet",
			"Cash Flow",
		],
		"Lending Reports": [
			"Loan Statement",
			"Arrear Reports",
			"Repayment Schedule",
		],
	},
	"LOS": {
		"Customer": [
			"Customer",
		],
		"Collateral": [
			"Collateral Type",
			"Collateral",
		],
		"Origination Setup": [
			"Workflow Configuration",
			"Pre-Screening",
			"Eligibility Rules & Formula",
			"Loan Product Assignment",
		],
		"Origination": [
			"Loan Application",
			"Prescreening",
			"Loan Appraisal",
			"Underwriting",
			"Offer Issuance",
		],
		"Accounting": [
			"General Ledger",
			"Trial Balance",
			"Receivable",
			"Payable",
			"Profit & Loss",
			"Balance Sheet",
			"Cash Flow",
		],
	},
}

def seed_sub_modules():
	"""Append default sub-module rows to each Custom Module that doesn't have them yet."""
	for product, modules in SUB_MODULES.items():
		for module_name, sub_module_names in modules.items():
			module = frappe.db.get_value(
				"Custom Module", {"product": product, "module_code": make_code(module_name)}
			)
			if not module:
				continue

			doc = frappe.get_doc("Custom Module", module)
			existing_codes = {row.sub_module_code for row in doc.sub_modules}
			added = False

			for sub_module_name in sub_module_names:
				sub_module_code = make_code(sub_module_name)
				if sub_module_code in existing_codes:
					continue

				doc.append(
					"sub_modules",
					{
						"sub_module_code": sub_module_code,
						"sub_module_name": sub_module_name,
						"is_active": 1,
					},
				)
				existing_codes.add(sub_module_code)
				added = True

			if added:
				doc.save(ignore_permissions=True)
