import frappe

from .product_seeder import seed_products
from .module_seeder import seed_modules
from .sub_module_seeder import seed_sub_modules

# Seeders run in this order on app install and on every migrate.
# Each seeder must be idempotent (only create records that don't exist).
SEEDERS = [
	seed_products,
	seed_modules,
	seed_sub_modules,
]


def run_all_seeders():
	for seeder in SEEDERS:
		seeder()

	frappe.db.commit()
