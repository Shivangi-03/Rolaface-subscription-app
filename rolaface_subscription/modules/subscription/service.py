import math
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import add_days, cint, getdate

from rolaface_subscription.modules.plan.constant import (
    MAX_PRICE,
    MODULE_DOCTYPE,
    PLAN_ACTIVE_STATUS,
    PLAN_DOCTYPE,
    PLAN_MODULES_FIELD,
    PRODUCT_DOCTYPE,
    RENEWAL_FIXED,
)
from rolaface_subscription.modules.subscription.constant import (
    BILLING_CUSTOM,
    CUSTOMER_DOCTYPE,
    DETAIL_FIELDS,
    FREQUENCY_MONTHS,
    LIST_COLUMNS,
    LIVE_STATUSES,
    MAX_BACKDATE_DAYS,
    MAX_FUTURE_START_DAYS,
    MODULE_ROW_FIELDS,
    MSG_NOT_FOUND,
    STATUS_SCHEDULED,
    STATUS_TRIALING,
    SUB_MODULE_DOCTYPE,
    SUB_MODULES_FIELD,
    SUBSCRIPTION_DOCTYPE,
    SUBSCRIPTION_SERIES,
)
from rolaface_subscription.modules.subscription.utils import (
    ACCESS_SQL,
    CENT,
    LIVE_SQL,
    STATUS_SQL,
    assert_not_stale,
    build_state,
    get_locked_subscription,
    money,
    named_lock,
    period_bounds,
    save_doc,
)
from rolaface_subscription.utils.api_response import ConflictError

_TABLE = f"`tab{SUBSCRIPTION_DOCTYPE}`"
_MODULE_TABLE = f"`tab{SUB_MODULE_DOCTYPE}`"


class SubscriptionService:
    # ================================================================== create
    @staticmethod
    def create_subscription(data: dict) -> dict:
        # same customer + same plan are processed one after the other (double-click safe)
        with named_lock(f"create|{data['customer']}|{data['plan']}"):
            return SubscriptionService._create(data)

    @staticmethod
    def _create(data: dict) -> dict:
        customer = SubscriptionService._get_customer(data["customer"])
        plan = SubscriptionService._get_plan(data["plan"])
        today = getdate()

        # idempotency: the same request_id returns the subscription it created the first time
        request_id = data.get("request_id")
        if request_id:
            existing = frappe.db.get_value(
                SUBSCRIPTION_DOCTYPE, {"request_id": request_id}, ["name", "customer", "plan"], as_dict=True
            )
            if existing:
                if existing.customer != customer.name or existing.plan != plan.name:
                    frappe.throw("request_id was already used for a different request", ConflictError)
                return {**SubscriptionService.get_subscription(existing.name), "idempotent_replay": True}

        # one live subscription per customer + plan
        live = frappe.db.sql(
            f"SELECT name FROM {_TABLE} WHERE customer = %(customer)s AND plan = %(plan)s "
            f"AND {LIVE_SQL} LIMIT 1",
            {"customer": customer.name, "plan": plan.name, "today": today},
        )
        if live:
            frappe.throw("This customer already has a live subscription for this plan", ConflictError)

        modules = SubscriptionService._resolve_plan_modules(plan)

        start = data["start_date"]
        if start < add_days(today, -MAX_BACKDATE_DAYS):
            frappe.throw(f"start_date cannot be more than {MAX_BACKDATE_DAYS} days in the past")
        if start > add_days(today, MAX_FUTURE_START_DAYS):
            frappe.throw(f"start_date cannot be more than {MAX_FUTURE_START_DAYS} days in the future")

        # billing period length in months (the plan's own, or Custom)
        plan_months = FREQUENCY_MONTHS.get(plan.billing_frequency)
        if not plan_months:
            frappe.throw(f"Plan has an unsupported billing frequency '{plan.billing_frequency}'")
        frequency = data.get("billing_frequency") or plan.billing_frequency
        months = data["custom_interval_months"] if frequency == BILLING_CUSTOM else FREQUENCY_MONTHS[frequency]

        subtotal, discount, grand_total = SubscriptionService._compute_pricing(
            money(plan.base_price), plan_months, months, data["discount_amount"]
        )

        # dates: the paid period starts when the trial ends (trial is extra free time)
        trial_days = cint(plan.trial_days) if cint(plan.trial_enabled) else 0
        trial_end = add_days(start, trial_days)
        fixed = plan.renewal_mode == RENEWAL_FIXED
        total_cycles = cint(plan.billing_cycles) if fixed else 0
        if fixed and total_cycles < 1:
            frappe.throw("Plan has invalid billing_cycles for Fixed Cycles")
        end_date = period_bounds(trial_end, months, total_cycles)[1] if fixed else None

        doc = frappe.get_doc(
            {
                "doctype": SUBSCRIPTION_DOCTYPE,
                "naming_series": SUBSCRIPTION_SERIES,
                "customer": customer.name,
                "customer_name": customer.customer_name,
                "plan": plan.name,
                "plan_name": plan.plan_name,
                "plan_code": plan.plan_code,
                "request_id": request_id,
                "pricing_model": plan.pricing_model,
                "plan_billing_frequency": plan.billing_frequency,
                "billing_frequency": frequency,
                "custom_interval_months": months if frequency == BILLING_CUSTOM else 0,
                "period_months": months,
                "currency": plan.currency,
                "plan_price": float(money(plan.base_price)),
                "setup_fee": float(money(plan.setup_fee)),
                "trial_enabled": 1 if trial_days else 0,
                "trial_days": trial_days,
                "renewal_mode": plan.renewal_mode,
                "billing_cycles": total_cycles,
                "user_limit": cint(plan.user_limit),
                "products": plan.products,
                "start_date": start,
                "trial_end_date": trial_end,
                "end_date": end_date,
                "subtotal": float(subtotal),
                "discount_amount": float(discount),
                "discount_reason": data.get("discount_reason"),
                "grand_total": float(grand_total),
                "notes": data.get("notes"),
                SUB_MODULES_FIELD: [
                    {
                        "module": m["module"],
                        "module_name": m["module_name"],
                        "product": m["product"],
                        "price": float(money(m["price"])),
                        "is_enabled": 1,
                    }
                    for m in modules
                ],
            }
        )
        doc.flags.via_service = True
        doc.insert(ignore_permissions=True)
        return SubscriptionService._detail(doc)

    @staticmethod
    def _compute_pricing(plan_price: Decimal, plan_months: int, months: int, discount: Decimal):
        """price per billing period = plan price x (chosen months / plan's months).
        For the plan's own frequency that is exactly the plan price; Custom is scaled.
        Tax is not calculated here: whoever creates the plan puts it in the base price."""
        if plan_price <= 0 or plan_price > MAX_PRICE:
            frappe.throw("The plan has an invalid price")
        subtotal = (plan_price * months / plan_months).quantize(CENT, rounding=ROUND_HALF_UP)
        if subtotal <= 0 or subtotal > MAX_PRICE:
            frappe.throw(f"The price per billing period must be between 0.01 and {MAX_PRICE}")
        if discount > subtotal:
            frappe.throw("discount_amount cannot be more than the price per billing period")
        return subtotal, discount, subtotal - discount

    # ------------------------------------------------------------ lookups
    @staticmethod
    def _get_customer(customer: str):
        row = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, ["name", "customer_name", "disabled"], as_dict=True)
        if not row:
            frappe.throw(f"Customer '{customer}' not found")
        if cint(row.disabled):
            frappe.throw(f"Customer '{row.name}' is disabled")
        return row

    @staticmethod
    def _get_plan(plan: str):
        try:
            doc = frappe.get_doc(PLAN_DOCTYPE, plan)  # loads the module rows too
        except frappe.DoesNotExistError:
            frappe.throw(f"Plan '{plan}' not found")
        if doc.status != PLAN_ACTIVE_STATUS:
            frappe.throw(f"Only Active plans can be subscribed, plan '{doc.name}' is '{doc.status}'")
        return doc

    @staticmethod
    def _resolve_plan_modules(plan) -> list[dict]:
        """The plan's modules as they are TODAY: every module and product must still be active."""
        rows = plan.get(PLAN_MODULES_FIELD) or []
        if not rows:
            frappe.throw("The plan has no modules")
        names = [r.module for r in rows]
        found = {
            m.name: m
            for m in frappe.get_all(
                MODULE_DOCTYPE,
                filters={"name": ["in", names]},
                fields=["name", "module_name", "product", "is_active"],
                limit_page_length=0,
            )
        }
        bad = [n for n in names if n not in found or not cint(found[n].is_active)]
        if bad:
            frappe.throw(f"The plan has module(s) that are missing or inactive: {', '.join(bad)}")
        products = sorted({found[n].product for n in names})
        active = set(
            frappe.get_all(
                PRODUCT_DOCTYPE,
                filters={"name": ["in", products], "is_active": 1},
                pluck="name",
                limit_page_length=0,
            )
        )
        bad_products = [p for p in products if p not in active]
        if bad_products:
            frappe.throw(f"The plan has product(s) that are missing or inactive: {', '.join(bad_products)}")
        return [
            {
                "module": r.module,
                "module_name": found[r.module].module_name,
                "product": found[r.module].product,
                "price": r.price or 0,
            }
            for r in rows
        ]

    # ================================================================== read
    @staticmethod
    def _detail(doc) -> dict:
        result = {field: doc.get(field) for field in DETAIL_FIELDS}
        result.update(build_state(doc, getdate()))
        result["modules"] = [{f: row.get(f) for f in MODULE_ROW_FIELDS} for row in doc.get(SUB_MODULES_FIELD)]
        return result

    @staticmethod
    def get_subscription(sub_id: str) -> dict:
        try:
            doc = frappe.get_doc(SUBSCRIPTION_DOCTYPE, sub_id)
        except frappe.DoesNotExistError:
            frappe.throw(MSG_NOT_FOUND.format(sub_id=sub_id), frappe.DoesNotExistError)
        return SubscriptionService._detail(doc)

    @staticmethod
    def get_subscriptions(params: dict) -> dict:
        today = getdate()
        page, page_size = params["page"], params["page_size"]

        where, values = ["1 = 1"], {"today": today}
        if params.get("status"):
            where.append(STATUS_SQL[params["status"]])  # fixed SQL text, no user input inside
        for key in ("customer", "plan"):
            if params.get(key):
                where.append(f"`{key}` = %({key})s")
                values[key] = params[key]
        if params.get("search"):
            where.append("(`name` LIKE %(search)s OR `customer_name` LIKE %(search)s)")
            values["search"] = f"%{params['search']}%"
        where_sql = " AND ".join(where)

        # sort_by / sort_order are whitelisted in validate_list_params
        order = f"`{params['sort_by']}` {params['sort_order'].upper()}"
        if params["sort_by"] != "name":
            order += ", `name` ASC"  # stable paging

        total = cint(frappe.db.sql(f"SELECT COUNT(*) FROM {_TABLE} WHERE {where_sql}", values)[0][0])
        columns = ", ".join(f"`{c}`" for c in LIST_COLUMNS)
        rows = frappe.db.sql(
            f"SELECT {columns} FROM {_TABLE} WHERE {where_sql} ORDER BY {order} "
            "LIMIT %(limit)s OFFSET %(offset)s",
            {**values, "limit": page_size, "offset": (page - 1) * page_size},
            as_dict=True,
        )
        for row in rows:
            row.update(build_state(row, today))
        return {
            "items": rows,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total else 0,
            },
        }

    @staticmethod
    def get_entitlements(customer: str) -> dict:
        """What may this customer use right now (Trialing or Active)?"""
        name = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, "name")
        if not name:
            frappe.throw(f"Customer '{customer}' not found", frappe.DoesNotExistError)
        today = getdate()
        subs = frappe.db.sql(
            "SELECT name, plan, plan_name, start_date, trial_end_date, end_date, cancelled_on, "
            f"period_months, renewal_mode, billing_cycles FROM {_TABLE} "
            f"WHERE customer = %(customer)s AND {ACCESS_SQL}",
            {"customer": name, "today": today},
            as_dict=True,
        )
        for sub in subs:
            sub.update(build_state(sub, today))

        modules = {}
        if subs:
            rows = frappe.db.sql(
                f"SELECT parent, module, module_name, product FROM {_MODULE_TABLE} "
                "WHERE parenttype = %(parenttype)s AND parentfield = %(parentfield)s "
                "AND is_enabled = 1 AND parent IN %(parents)s",
                {
                    "parenttype": SUBSCRIPTION_DOCTYPE,
                    "parentfield": SUB_MODULES_FIELD,
                    "parents": tuple(s.name for s in subs),
                },
                as_dict=True,
            )
            for r in rows:
                entry = modules.setdefault(
                    r.module,
                    {"module": r.module, "module_name": r.module_name, "product": r.product, "subscriptions": []},
                )
                entry["subscriptions"].append(r.parent)
        return {"customer": name, "has_access": bool(subs), "subscriptions": subs, "modules": list(modules.values())}

    # ================================================================== update
    @staticmethod
    def update_subscription(params: dict) -> dict:
        params = dict(params)
        sub_id = params.pop("id")
        expected_modified = params.pop("modified", None)

        doc = get_locked_subscription(sub_id)
        status = build_state(doc, getdate())["status"]
        if status not in LIVE_STATUSES:
            frappe.throw(f"A {status} subscription cannot be edited", ConflictError)
        assert_not_stale(doc, expected_modified)

        changed = False
        if "discount_amount" in params:
            discount = params["discount_amount"]
            if discount > money(doc.subtotal):
                frappe.throw("discount_amount cannot be more than the price per billing period")
            if discount != money(doc.discount_amount):
                doc.discount_amount = float(discount)
                doc.grand_total = float(money(doc.subtotal) - discount)
                changed = True
        for field in ("discount_reason", "notes"):
            if field in params and (params[field] or None) != (doc.get(field) or None):
                doc.set(field, params[field])
                changed = True

        if changed:
            save_doc(doc)  # Frappe's own version history (Track Changes) records who changed what
        return SubscriptionService._detail(doc)

    @staticmethod
    def cancel_subscription(params: dict) -> dict:
        doc = get_locked_subscription(params["id"])
        today = getdate()
        state = build_state(doc, today)
        if state["status"] not in LIVE_STATUSES:
            frappe.throw(f"Subscription is already {state['status']}", ConflictError)
        assert_not_stale(doc, params.get("modified"))

        # nothing has been paid for before the trial ends, so Scheduled / Trialing always end now
        immediate = params["immediate"] or state["status"] in (STATUS_SCHEDULED, STATUS_TRIALING)
        if immediate:
            doc.cancelled_on = today
        else:
            if state["cancel_scheduled"]:
                frappe.throw("Cancellation at period end is already scheduled", ConflictError)
            doc.cancelled_on = state["current_period_end"]  # takes effect on that date, no job needed
        doc.cancel_reason = params["reason"]
        save_doc(doc)
        return SubscriptionService._detail(doc)