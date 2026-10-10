import hashlib
import math
from contextlib import contextmanager, nullcontext
from decimal import Decimal

import frappe
from frappe.utils import cint

from rolaface_subscription.modules.plan.constant import (
    CURRENCY_DOCTYPE,
    MAX_PRICE,
    MAX_VARCHAR,
    MODULE_DOCTYPE,
    MSG_PLAN_NOT_FOUND,
    PLAN_ACTIVE_STATUS,
    PLAN_DOCTYPE,
    PLAN_EDITABLE_STATUS,
    PLAN_MODULE_DOCTYPE,
    PLAN_MODULE_FIELDS,
    PLAN_MODULES_FIELD,
    PLAN_STATUS_TRANSITIONS,
    PLAN_UPDATABLE_FIELDS,
    PRICING_FLAT,
    PRICING_PER_MODULE,
    PRODUCT_DOCTYPE,
    RENEWAL_FIXED,
    RETURN_FIELDS_GET_ALL,
    RETURN_FIELDS_GET_BY_ID,
)
from rolaface_subscription.modules.plan.utils import (
    assert_not_stale,
    assert_price_precision,
    assert_trial_and_renewal_rules,
    get_locked_plan,
    save_doc,
    split_products,
    to_db_value,
)
from rolaface_subscription.utils.api_response import ConflictError

class PlanService:
    @staticmethod
    def create_plan(data: dict) -> dict:
        with PlanService._plan_name_lock(data["plan_name"]):
            return PlanService._create_plan(data)

    @staticmethod
    def _create_plan(data: dict) -> dict:
        assert_price_precision()
        # 1. currency must exist and be enabled
        currency = PlanService._get_enabled_currency(data["currency"])

        # 2. plan_name must be unique
        if PlanService._plan_name_exists(data["plan_name"]):
            frappe.throw(f"A plan named '{data['plan_name']}' already exists", ConflictError)

        # 3. modules must exist and be active; product is read from DB
        modules = PlanService._resolve_modules(data["modules"])
        product_codes = PlanService._resolve_products(modules)
        products_value = PlanService._products_value(product_codes)

        # 4. pricing is computed on the server
        base_price, module_rows = PlanService._apply_pricing(
            data["pricing_model"], data.get("base_price"), modules, currency
        )

        values = {
            "doctype": PLAN_DOCTYPE,
            "plan_name": data["plan_name"],
            "user_limit": data["user_limit"],
            "description": data.get("description"),
            "status": data["status"],  # always Draft (forced in validate_create_payload)
            "products": products_value,
            "billing_frequency": data["billing_frequency"],
            "pricing_model": data["pricing_model"],
            "currency": currency,
            "base_price": to_db_value(base_price),
            "setup_fee": to_db_value(data["setup_fee"]),
            "trial_enabled": 1 if data["trial_enabled"] else 0,
            "trial_days": data["trial_days"] if data["trial_enabled"] else 0,
            "renewal_mode": data["renewal_mode"],
            "billing_cycles": data["billing_cycles"] if data["renewal_mode"] == RENEWAL_FIXED else 0,
            PLAN_MODULES_FIELD: module_rows,
        }
        doc = PlanService._insert_doc(values)

        return {
            "name": doc.name,
            "plan_name": doc.plan_name,
            "products": product_codes,
            "status": doc.status,
            "pricing_model": doc.pricing_model,
            "base_price": doc.base_price,
            "module_count": len(module_rows),
            "modified": doc.modified,
        }

    @staticmethod
    def _insert_doc(values: dict):
        doc = frappe.get_doc(values)
        doc.insert(ignore_permissions=True)
        return doc

    @staticmethod
    def _resolve_modules(requested: list[dict]) -> list[dict]:
        names = [m["module"] for m in requested]
        if len(set(names)) != len(names):
            frappe.throw("Duplicate modules selected")

        found = {r.name: r for r in PlanService._get_modules_by_names(names)}
        missing = [n for n in names if n not in found]
        if missing:
            frappe.throw(f"Module(s) not found: {', '.join(missing)}")
        inactive = [n for n in names if not cint(found[n].is_active)]
        if inactive:
            frappe.throw(f"Module(s) are inactive: {', '.join(inactive)}")

        return [
            {
                "module": m["module"],
                "module_name": found[m["module"]].module_name,
                "product": found[m["module"]].product,
                "price": m.get("price"),
            }
            for m in requested  
        ]

    @staticmethod
    def _resolve_products(modules: list[dict]) -> list[str]:
        """every module's product must exist AND be active. Returns sorted product codes."""
        names = sorted({str(m["product"]) for m in modules})
        rows = frappe.get_all(
            PRODUCT_DOCTYPE,
            filters={"name": ["in", names], "is_active": 1},
            fields=["name", "product_code"],
            limit_page_length=0,
        )
        lookup = {r.name: (r.product_code or r.name) for r in rows}
        bad = [n for n in names if n not in lookup]
        if bad:
            frappe.throw(f"Product(s) not found or inactive: {', '.join(bad)}")
        with_comma = [c for c in lookup.values() if "," in c]
        if with_comma: 
            frappe.throw(f"Product code(s) contain a comma and cannot be used in a plan: {', '.join(with_comma)}")
        return sorted(set(lookup.values()))

    @staticmethod
    def _products_value(product_codes: list[str]) -> str:
        value = ",".join(product_codes)
        if len(value) > MAX_VARCHAR:  # Data field is 140 chars
            frappe.throw("Too many products selected for one plan")
        return value

    @staticmethod
    def _apply_pricing(pricing_model: str, base_price_input, modules: list[dict], currency: str):
        if pricing_model == PRICING_FLAT:
            if base_price_input is None or base_price_input <= 0:
                frappe.throw("base_price must be greater than 0 for Flat pricing")
            if base_price_input > MAX_PRICE:
                frappe.throw(f"base_price cannot be more than {MAX_PRICE}")
            base_price = base_price_input
            prices = [Decimal("0.00")] * len(modules)  
        else:
            prices = [m.get("price") for m in modules]
            for module, price in zip(modules, prices):
                if price is None or price <= 0:
                    frappe.throw(f"Price of module '{module['module']}' must be greater than 0")
            base_price = sum(prices, Decimal("0.00"))
            if base_price > MAX_PRICE:
                frappe.throw(f"Total of module prices cannot be more than {MAX_PRICE}")
            if base_price_input is not None and base_price_input != base_price:
                frappe.throw(
                    f"base_price ({base_price_input}) does not match the sum of module prices "
                    f"({base_price}); omit base_price for Per Module plans"
                )

        rows = [
            {
                "module": m["module"],
                "module_name": m["module_name"],
                "product": m["product"],
                "price": to_db_value(price),
                "currency": currency,
            }
            for m, price in zip(modules, prices)
        ]
        return base_price, rows


    @staticmethod
    def _get_modules_by_names(names: list[str]) -> list[dict]:
        return frappe.get_all(
            MODULE_DOCTYPE,
            filters={"name": ["in", names]},
            fields=["name", "module_name", "product", "is_active"],
            limit_page_length=0,
        )

    @staticmethod
    def _get_enabled_currency(currency: str) -> str:
        name = frappe.db.get_value(CURRENCY_DOCTYPE, {"name": currency, "enabled": 1}, "name")
        if not name:
            frappe.throw(f"Currency '{currency}' does not exist or is disabled")
        return name

    @staticmethod
    @contextmanager
    def _plan_name_lock(plan_name: str):
        key = "plan_name:" + hashlib.md5(" ".join(plan_name.split()).casefold().encode()).hexdigest()
        if frappe.db.sql("SELECT GET_LOCK(%s, 10)", (key,))[0][0] != 1:
            frappe.throw("Another request is saving a plan with this name, please retry", ConflictError)
        try:
            frappe.db.commit()
            yield
            frappe.db.commit()
        finally:
            frappe.db.sql("SELECT RELEASE_LOCK(%s)", (key,))

    @staticmethod
    def _plan_name_exists(plan_name: str, exclude: str | None = None) -> bool:
        filters = {"plan_name": plan_name}
        if exclude:
            filters["name"] = ["!=", exclude]
        return bool(frappe.db.exists(PLAN_DOCTYPE, filters))

    
    @staticmethod
    def get_plans(params: dict) -> dict:
        page, page_size = params["page"], params["page_size"]

        filters = {
            key: params[key]
            for key in ("status", "pricing_model", "billing_frequency")
            if params.get(key)
        }

        if params.get("product"):
            plan_names = PlanService._get_plan_names_by_product(params["product"])
            if not plan_names:
                return PlanService._list_result([], 0, page, page_size)
            filters["name"] = ["in", plan_names]

        or_filters = None
        if params.get("search"):
            pattern = f"%{params['search']}%"
            or_filters = [["plan_name", "like", pattern], ["name", "like", pattern]]

        order_by = f"{params['sort_by']} {params['sort_order']}"  # sort_by is whitelisted
        if params["sort_by"] != "name":
            order_by += ", name asc" 

        count_rows = frappe.get_all(
            PLAN_DOCTYPE,
            filters=filters,
            or_filters=or_filters,
            fields=[{"COUNT": "name", "as": "total"}],
            order_by="",
            limit_page_length=1,
        )
        total = cint(count_rows[0].get("total", next(iter(count_rows[0].values()), 0))) if count_rows else 0

        rows = frappe.get_all(
            PLAN_DOCTYPE,
            filters=filters,
            or_filters=or_filters,
            fields=RETURN_FIELDS_GET_ALL,
            order_by=order_by,
            limit_start=(page - 1) * page_size,
            limit_page_length=page_size,
        )
        for row in rows:
            row["products"] = split_products(row.get("products"))

        return PlanService._list_result(rows, total, page, page_size)

    @staticmethod
    def get_plan(plan_id: str) -> dict:
        return PlanService._load_plan(plan_id)

    @staticmethod
    def _load_plan(plan_id: str) -> dict:
        plan = frappe.db.get_value(PLAN_DOCTYPE, plan_id, RETURN_FIELDS_GET_BY_ID, as_dict=True)
        if not plan:
            frappe.throw(MSG_PLAN_NOT_FOUND.format(plan_id=plan_id), frappe.DoesNotExistError)

        plan["products"] = split_products(plan.get("products"))
        modules = frappe.get_all(
            PLAN_MODULE_DOCTYPE,
            filters={"parent": plan["name"], "parenttype": PLAN_DOCTYPE, "parentfield": PLAN_MODULES_FIELD},
            fields=list(PLAN_MODULE_FIELDS),
            order_by="idx asc",
            limit_page_length=0,
            parent_doctype=PLAN_DOCTYPE,
        )
        plan["modules"] = modules
        return plan

    @staticmethod
    def _get_plan_names_by_product(product: str) -> list[str]:
        rows = frappe.get_all(
            PLAN_MODULE_DOCTYPE,
            filters={"product": product, "parenttype": PLAN_DOCTYPE, "parentfield": PLAN_MODULES_FIELD},
            pluck="parent",
            limit_page_length=0,
            parent_doctype=PLAN_DOCTYPE,
        )
        return sorted(set(rows))

    @staticmethod
    def _list_result(items: list, total: int, page: int, page_size: int) -> dict:
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total else 0,
            },
        }


    @staticmethod
    def update_plan(params: dict) -> dict:
        lock = PlanService._plan_name_lock(params["plan_name"]) if "plan_name" in params else nullcontext()
        with lock:
            return PlanService._update_plan(params)

    @staticmethod
    def _update_plan(params: dict) -> dict:
        assert_price_precision()
        params = dict(params)
        plan_id = params.pop("id")
        expected_modified = params.pop("modified", None)

        if "status" in params:
            frappe.throw("status cannot be changed here, use the update_status API")
        if not params:
            frappe.throw("Nothing to update, send at least one field")

        doc = get_locked_plan(plan_id)  # row lock held until commit / rollback

        if doc.status != PLAN_EDITABLE_STATUS:
            frappe.throw(
                f"Only {PLAN_EDITABLE_STATUS} plans can be edited, this plan is '{doc.status}'",
                ConflictError,
            )

        assert_not_stale(doc, expected_modified)

        if "plan_name" in params and PlanService._plan_name_exists(params["plan_name"], exclude=doc.name):
            frappe.throw(f"A plan named '{params['plan_name']}' already exists", ConflictError)

        if "currency" in params:
            params["currency"] = PlanService._get_enabled_currency(params["currency"])

        current = {
            "pricing_model": doc.pricing_model,
            "currency": doc.currency,
            "base_price": Decimal(str(doc.base_price or 0)),
            "trial_enabled": bool(doc.trial_enabled),
            "trial_days": doc.trial_days or 0,
            "renewal_mode": doc.renewal_mode,
            "billing_cycles": doc.billing_cycles or 0,
        }
        merged = {**current, **{k: v for k, v in params.items() if k in current}}

        switching_model = merged["pricing_model"] != current["pricing_model"]
        currency_changed = merged["currency"] != current["currency"]

        if switching_model or currency_changed:
            what = "switching pricing_model" if switching_model else "changing currency"
            if merged["pricing_model"] == PRICING_PER_MODULE and "modules" not in params:
                frappe.throw(f"Send modules with prices when {what}")
            if merged["pricing_model"] == PRICING_FLAT and "base_price" not in params:
                frappe.throw(f"Send base_price when {what}")

        assert_trial_and_renewal_rules(
            merged["trial_enabled"], merged["trial_days"], merged["renewal_mode"], merged["billing_cycles"]
        )
        if not merged["trial_enabled"]:
            merged["trial_days"] = 0
        if merged["renewal_mode"] != RENEWAL_FIXED:
            merged["billing_cycles"] = 0

        # modules: sent -> replace the whole list; not sent -> keep as they are
        products_value = None
        if "modules" in params:
            modules = PlanService._resolve_modules(params["modules"])
            products_value = PlanService._products_value(PlanService._resolve_products(modules))
        else:
            modules = PlanService._modules_from_doc(doc)

        flat = merged["pricing_model"] == PRICING_FLAT
        base_price_input = merged["base_price"] if flat else params.get("base_price")
        base_price, module_rows = PlanService._apply_pricing(
            merged["pricing_model"], base_price_input, modules, merged["currency"]
        )
        merged["base_price"] = base_price
        rebuild_rows = "modules" in params or switching_model or currency_changed

        for field in PLAN_UPDATABLE_FIELDS:
            if field in merged:
                value = merged[field]
            elif field in params:
                value = params[field]
            else:
                continue
            doc.set(field, to_db_value(value))

        if products_value is not None:
            doc.set("products", products_value)
        if rebuild_rows:
            doc.set(PLAN_MODULES_FIELD, module_rows)

        save_doc(doc)
        return PlanService._load_plan(doc.name)

    @staticmethod
    def _modules_from_doc(doc) -> list[dict]:
        """existing rows as they are stored (no DB re-resolution)"""
        return [
            {
                "module": row.module,
                "module_name": row.module_name,
                "product": row.product,
                "price": Decimal(str(row.price)) if row.price is not None else None,
            }
            for row in doc.get(PLAN_MODULES_FIELD)
        ]

    @staticmethod
    def update_plan_status(params: dict) -> dict:
        plan_id = params["id"]
        new_status = params["status"]

        doc = get_locked_plan(plan_id)
        assert_not_stale(doc, params.get("modified"))

        if doc.status == new_status:
            frappe.throw(f"Plan is already '{new_status}'", ConflictError)
        if new_status not in PLAN_STATUS_TRANSITIONS.get(doc.status, ()):
            frappe.throw(f"Cannot change status from '{doc.status}' to '{new_status}'", ConflictError)

        if new_status == PLAN_ACTIVE_STATUS:
            PlanService._prepare_for_activation(doc)

        doc.set("status", new_status)
        save_doc(doc)
        return PlanService._load_plan(doc.name)

    @staticmethod
    def _prepare_for_activation(doc) -> None:
        rows = doc.get(PLAN_MODULES_FIELD)
        if not rows:
            frappe.throw("Cannot activate a plan without modules")

        currency = PlanService._get_enabled_currency(doc.currency)

        modules = PlanService._resolve_modules(
            [
                {
                    "module": r.module,
                    "price": Decimal(str(r.price)) if r.price is not None else None,
                }
                for r in rows
            ]
        )
        products_value = PlanService._products_value(PlanService._resolve_products(modules))

        flat = doc.pricing_model == PRICING_FLAT
        base_price, _ = PlanService._apply_pricing(
            doc.pricing_model,
            Decimal(str(doc.base_price or 0)) if flat else None,
            modules,
            currency,
        )

        for row, module in zip(rows, modules):
            row.module_name = module["module_name"]
            row.product = module["product"]

        doc.set("products", products_value)
        doc.set("base_price", to_db_value(base_price))