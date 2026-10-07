import math
from decimal import ROUND_HALF_UP, Decimal
import frappe
from frappe.utils import add_days, cint, getdate
from rolaface_subscription.modules.plan.constant import (
    CURRENCY_DOCTYPE,
    MAX_PRICE,
    MODULE_DOCTYPE,
    PLAN_ACTIVE_STATUS,
    PLAN_DOCTYPE,
    PLAN_MODULE_DOCTYPE,
    PLAN_MODULES_FIELD,
    PRODUCT_DOCTYPE,
    RENEWAL_AUTO,
    RENEWAL_FIXED,
)
from rolaface_subscription.modules.subscription.constant import (
    ACCESS_STATUSES,
    BILLING_CUSTOM,
    CUSTOMER_DOCTYPE,
    DETAIL_FIELDS,
    ENDED_STATUSES,
    FREQUENCY_MONTHS,
    LIST_COLUMNS,
    LIVE_STATUSES,
    MAX_BACKDATE_DAYS,
    MAX_FUTURE_START_DAYS,
    MODULE_ROW_FIELDS,
    MSG_NOT_FOUND,
    OPEN_STATUSES,
    STATUS_ACTIVE,
    STATUS_DRAFT,
    STATUS_SCHEDULED,
    STATUS_TRIALING,
    SUB_MODULE_DOCTYPE,
    SUB_MODULES_FIELD,
    SUBSCRIPTION_DOCTYPE,
    SUBSCRIPTION_SERIES,
)
from rolaface_subscription.modules.subscription.utils import (
    CENT,
    assert_not_stale,
    build_state,
    get_locked_subscription,
    money,
    named_lock,
    period_bounds,
    save_doc,
)
from rolaface_subscription.utils.api_response import ConflictError

# fields needed to work out a subscription's billing period (build_state)
STATE_COLUMNS = [
    "name", "status", "plan", "plan_name", "start_date", "trial_end_date", "end_date", "cancelled_on",
    "period_months", "renewal_mode", "billing_cycles",
]


class SubscriptionService:
    @staticmethod
    def create_subscription(data: dict) -> dict:
        with named_lock(f"create|{data['customer']}|{data['plan']}"):
            doc = SubscriptionService._create(data)
        return SubscriptionService._detail(doc)

    @staticmethod
    def submit_subscription(params: dict) -> dict:
        row = frappe.db.get_value(SUBSCRIPTION_DOCTYPE, params["id"], ["customer", "plan"], as_dict=True)
        if not row:
            frappe.throw(MSG_NOT_FOUND.format(sub_id=params["id"]), frappe.DoesNotExistError)

        # same lock as create, so a second subscription for this customer + plan cannot sneak in
        with named_lock(f"create|{row.customer}|{row.plan}"):
            doc = get_locked_subscription(params["id"])
            if doc.docstatus != 0 or doc.status != STATUS_DRAFT:
                frappe.throw(f"Only Draft subscriptions can be submitted, this one is {doc.status}", ConflictError)
            assert_not_stale(doc, params.get("modified"))
            doc.submit()  # status + customer site sync happen in doc_events.before_submit / on_submit
        return SubscriptionService._detail(doc)

    @staticmethod
    def _create(data: dict):
        customer = SubscriptionService._get_customer(data["customer"])
        plan = SubscriptionService._get_plan(data["plan"])
        today = getdate()


        if frappe.db.exists(
            SUBSCRIPTION_DOCTYPE,
            {"customer": customer.name, "plan": plan.name, "status": ["in", OPEN_STATUSES]},
        ):
            frappe.throw("This customer already has a draft or live subscription for this plan", ConflictError)

        modules = SubscriptionService._resolve_plan_modules(plan)

        start = data["start_date"]
        if start < add_days(today, -MAX_BACKDATE_DAYS):
            frappe.throw(f"start_date cannot be more than {MAX_BACKDATE_DAYS} days in the past")
        if start > add_days(today, MAX_FUTURE_START_DAYS):
            frappe.throw(f"start_date cannot be more than {MAX_FUTURE_START_DAYS} days in the future")

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
                "grand_total": float(grand_total),
                "notes": data.get("notes"),
                "auto_sync": 1 if data.get("auto_sync", True) else 0,
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
        doc.status = STATUS_DRAFT
        doc.flags.via_service = True
        doc.insert(ignore_permissions=True)
        return doc

    @staticmethod
    def _compute_pricing(plan_price: Decimal, plan_months: int, months: int, discount: Decimal):
        if plan_price <= 0 or plan_price > MAX_PRICE:
            frappe.throw("The plan has an invalid price")
        subtotal = (plan_price * months / plan_months).quantize(CENT, rounding=ROUND_HALF_UP)
        if subtotal <= 0 or subtotal > MAX_PRICE:
            frappe.throw(f"The price per billing period must be between 0.01 and {MAX_PRICE}")
        if discount > subtotal:
            frappe.throw("discount_amount cannot be more than the price per billing period")
        return subtotal, discount, subtotal - discount

    @staticmethod
    def _get_customer(customer: str):
        row = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, ["name", "customer_name", "disabled"], as_dict=True)
        if not row:
            frappe.throw(f"Customer '{customer}' not found", frappe.DoesNotExistError)
        if cint(row.disabled):
            frappe.throw(f"Customer '{row.name}' is disabled")
        return row

    @staticmethod
    def _get_plan(plan: str):
        try:
            doc = frappe.get_doc(PLAN_DOCTYPE, plan)  # loads the module rows too
        except frappe.DoesNotExistError:
            frappe.throw(f"Plan '{plan}' not found", frappe.DoesNotExistError)
        if doc.status != PLAN_ACTIVE_STATUS:
            frappe.throw(f"Only Active plans can be subscribed, plan '{doc.name}' is '{doc.status}'")
        return doc

    @staticmethod
    def _resolve_plan_modules(plan) -> list[dict]:
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

        filters = {key: params[key] for key in ("status", "customer", "plan") if params.get(key)}
        or_filters = None
        if params.get("search"):
            search = f"%{params['search']}%"
            or_filters = {"name": ["like", search], "customer_name": ["like", search]}

        order = f"{params['sort_by']} {params['sort_order']}"  # sort_by / sort_order are allow-listed
        if params["sort_by"] != "name":
            order += ", name asc"

        total = cint(
            frappe.get_all(
                SUBSCRIPTION_DOCTYPE, filters=filters, or_filters=or_filters, fields=[{"COUNT": "*", "as": "total"}]
            )[0].total
        )
        rows = frappe.get_all(
            SUBSCRIPTION_DOCTYPE,
            filters=filters,
            or_filters=or_filters,
            fields=LIST_COLUMNS,
            order_by=order,
            limit_start=(page - 1) * page_size,
            limit_page_length=page_size,
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
        subs = frappe.get_all(
            SUBSCRIPTION_DOCTYPE,
            filters={"customer": name, "status": ["in", ACCESS_STATUSES]},
            fields=STATE_COLUMNS,
            order_by="creation asc",
            limit_page_length=0,
        )
        for sub in subs:
            sub.update(build_state(sub, today))

        modules = {}
        if subs:
            rows = frappe.get_all(
                SUB_MODULE_DOCTYPE,
                filters={
                    "parenttype": SUBSCRIPTION_DOCTYPE,
                    "parentfield": SUB_MODULES_FIELD,
                    "is_enabled": 1,
                    "parent": ["in", [s.name for s in subs]],
                },
                fields=["parent", "module", "module_name", "product"],
                order_by="parent asc, idx asc",
                limit_page_length=0,
            )
            for r in rows:
                entry = modules.setdefault(
                    r.module,
                    {"module": r.module, "module_name": r.module_name, "product": r.product, "subscriptions": []},
                )
                entry["subscriptions"].append(r.parent)
        return {"customer": name, "has_access": bool(subs), "subscriptions": subs, "modules": list(modules.values())}

    @staticmethod
    def update_subscription(params: dict) -> dict:
        params = dict(params)
        sub_id = params.pop("id")
        expected_modified = params.pop("modified", None)

        doc = get_locked_subscription(sub_id)
        if doc.status not in OPEN_STATUSES:
            frappe.throw(f"A {doc.status} subscription cannot be edited", ConflictError)
        assert_not_stale(doc, expected_modified)

        changed = False
        if "discount_amount" in params:
            if doc.docstatus != 0:
                frappe.throw("discount_amount can only be changed while the subscription is a Draft", ConflictError)
            discount = params["discount_amount"]
            if discount > money(doc.subtotal):
                frappe.throw("discount_amount cannot be more than the price per billing period")
            if discount != money(doc.discount_amount):
                doc.discount_amount = float(discount)
                doc.grand_total = float(money(doc.subtotal) - discount)
                changed = True
        if "auto_sync" in params:
            if doc.docstatus != 0:
                frappe.throw("auto_sync can only be changed while the subscription is a Draft", ConflictError)
            if cint(params["auto_sync"]) != cint(doc.auto_sync):
                doc.auto_sync = cint(params["auto_sync"])
                changed = True
        for field in ("notes",):
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
        if doc.status == STATUS_DRAFT:
            frappe.throw("A Draft subscription cannot be cancelled, it was never submitted", ConflictError)
        if doc.status not in LIVE_STATUSES:
            frappe.throw(f"Subscription is already {doc.status}", ConflictError)
        assert_not_stale(doc, params.get("modified"))

        immediate = params["immediate"] or doc.status in (STATUS_SCHEDULED, STATUS_TRIALING)
        doc.cancel_reason = params["reason"]
        if immediate:
            doc.cancelled_on = today
            doc.flags.ignore_permissions = True
            doc.cancel()  # Frappe cancel: docstatus 2, status set in doc_events.before_cancel
        else:
            if state["cancel_scheduled"]:
                frappe.throw("Cancellation at period end is already scheduled", ConflictError)
            if doc.end_date and getdate(state["current_period_end"]) >= getdate(doc.end_date):
                frappe.throw(f"This subscription already ends on {doc.end_date}, no cancellation needed. "
                "Use immediate cancel if you want to stop access now.", ConflictError,)
            doc.cancelled_on = state["current_period_end"]  # the daily status job cancels it on that date
            save_doc(doc)
        return SubscriptionService._detail(doc)

    @staticmethod
    def _currency_symbols(currencies) -> dict:
        names = sorted({c for c in currencies if c})
        if not names:
            return {}
        rows = frappe.get_all(
            CURRENCY_DOCTYPE, filters={"name": ["in", names]}, fields=["name", "symbol"], limit_page_length=0
        )
        return {r.name: r.symbol for r in rows}

    @staticmethod
    def _product_breakdown(module_rows: list[dict]) -> list[dict]:
        included = {}
        for row in module_rows:
            if cint(row.get("is_enabled")):
                included.setdefault(row["product"], []).append(
                    {"module": row["module"], "module_name": row["module_name"]}
                )
        products = frappe.get_all(
            PRODUCT_DOCTYPE, fields=["name", "product_code", "product_name", "is_active"], limit_page_length=0
        )
        totals = {
            row.product: cint(row.module_count)
            for row in frappe.get_all(
                MODULE_DOCTYPE,
                filters={"is_active": 1},
                fields=["product", {"COUNT": "*", "as": "module_count"}],
                group_by="product",
                order_by="product asc",
            )
        }
        result = []
        for product in products:
            modules = included.get(product.name, [])
            if not cint(product.is_active) and not modules:
                continue  # an inactive product is only shown if the customer still has modules of it
            result.append(
                {
                    "product": product.name,
                    "product_code": product.product_code or product.name,
                    "product_name": product.product_name,
                    "included": bool(modules),
                    "included_count": len(modules),
                    "total_modules": max(totals.get(product.name, 0), len(modules)),
                    "included_modules": modules,
                }
            )
        result.sort(key=lambda p: (not p["included"], (p["product_name"] or "").lower()))
        return result

    @staticmethod
    def get_my_subscription(customer: str) -> dict:
        """'My Subscription' screen: the customer's current subscription with dates, price and a
        card for every product (included or not).
        Current = Active, then Trialing, then Scheduled (newest start first). If the customer has
        none of those, the most recent ended one is returned so the screen can say Expired / Cancelled."""
        cust = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, ["name", "customer_name"], as_dict=True)
        if not cust:
            frappe.throw(f"Customer '{customer}' not found", frappe.DoesNotExistError)
        today = getdate()

        def fetch(status_filter, limit):
            return frappe.get_all(
                SUBSCRIPTION_DOCTYPE,
                filters={"customer": cust.name, "status": status_filter},
                fields=STATE_COLUMNS,
                order_by="start_date desc, creation desc",
                limit_page_length=limit,
            )

        live_rows = fetch(["in", LIVE_STATUSES], 100)
        ended_rows = fetch(["in", ENDED_STATUSES], 20)
        rows = live_rows + ended_rows
        result = {
            "customer": cust.name,
            "customer_name": cust.customer_name,
            "has_subscription": bool(rows),
            "subscription": None,
            "other_subscriptions": [],
        }
        if not rows:
            return result

        for row in rows:
            row.update(build_state(row, today))
        priority = {STATUS_ACTIVE: 0, STATUS_TRIALING: 1, STATUS_SCHEDULED: 2}
        rows.sort(key=lambda r: priority.get(r["status"], 3))  # stable: newest start stays first

        detail = SubscriptionService._detail(frappe.get_doc(SUBSCRIPTION_DOCTYPE, rows[0].name))
        symbols = SubscriptionService._currency_symbols([detail["currency"]])
        expiry = getdate(detail["expiry_date"]) if detail["expiry_date"] else None
        detail["currency_symbol"] = symbols.get(detail["currency"])
        detail["days_left"] = max((expiry - today).days, 0) if expiry else None
        detail["auto_renew"] = detail["renewal_mode"] == RENEWAL_AUTO and not detail["cancelled_on"]
        detail["products"] = SubscriptionService._product_breakdown(detail["modules"])

        result["subscription"] = detail
        result["other_subscriptions"] = [
            {
                "name": r.name,
                "plan": r.plan,
                "plan_name": r.plan_name,
                "status": r["status"],
                "start_date": r.start_date,
                "expiry_date": r["expiry_date"],
            }
            for r in rows[1:]
        ]
        return result

    @staticmethod
    def get_available_plans(params: dict) -> dict:
        page, page_size = params["page"], params["page_size"]

        current_plans = set()
        if params.get("customer"):
            customer = frappe.db.get_value(CUSTOMER_DOCTYPE, params["customer"], "name")
            if not customer:
                frappe.throw(f"Customer '{params['customer']}' not found", frappe.DoesNotExistError)
            current_plans = set(
                frappe.get_all(
                    SUBSCRIPTION_DOCTYPE,
                    filters={"customer": customer, "status": ["in", LIVE_STATUSES]},
                    pluck="plan",
                    limit_page_length=0,
                )
            )

        total = frappe.db.count(PLAN_DOCTYPE, {"status": PLAN_ACTIVE_STATUS})
        plans = frappe.get_all(
            PLAN_DOCTYPE,
            filters={"status": PLAN_ACTIVE_STATUS},
            fields=[
                "name", "plan_name", "plan_code", "description", "pricing_model", "billing_frequency", "currency",
                "base_price", "setup_fee", "trial_enabled", "trial_days", "renewal_mode", "billing_cycles",
                "user_limit",
            ],
            order_by="base_price asc, plan_name asc, name asc",
            limit_start=(page - 1) * page_size,
            limit_page_length=page_size,
        )

        counts = {}  # plan -> product -> number of modules
        if plans:
            for row in frappe.get_all(
                PLAN_MODULE_DOCTYPE,
                filters={
                    "parenttype": PLAN_DOCTYPE,
                    "parentfield": PLAN_MODULES_FIELD,
                    "parent": ["in", [p.name for p in plans]],
                },
                fields=["parent", "product", {"COUNT": "*", "as": "module_count"}],
                group_by="parent, product",
                order_by="parent asc, product asc",
                limit_page_length=0,
            ):
                counts.setdefault(row.parent, {})[row.product] = cint(row.module_count)

        products = frappe.get_all(
            PRODUCT_DOCTYPE, fields=["name", "product_code", "product_name", "is_active"], limit_page_length=0
        )
        by_name = {p.name: p for p in products}
        active_products = [p for p in products if cint(p.is_active)]
        symbols = SubscriptionService._currency_symbols([p.currency for p in plans])

        items = []
        for plan in plans:
            per_product = counts.get(plan.name, {})
            included = []
            for code, number in per_product.items():
                product = by_name.get(code)
                included.append(
                    {
                        "product": code,
                        "product_code": (product.product_code if product else None) or code,
                        "product_name": product.product_name if product else code,
                        "module_count": number,
                    }
                )
            included.sort(key=lambda p: (p["product_name"] or "").lower())
            excluded = [
                {"product": p.name, "product_code": p.product_code or p.name, "product_name": p.product_name}
                for p in active_products
                if p.name not in per_product
            ]
            items.append(
                {
                    "name": plan.name,
                    "plan_name": plan.plan_name,
                    "plan_code": plan.plan_code,
                    "description": plan.description,
                    "pricing_model": plan.pricing_model,
                    "billing_frequency": plan.billing_frequency,
                    "currency": plan.currency,
                    "currency_symbol": symbols.get(plan.currency),
                    "price": plan.base_price,
                    "setup_fee": plan.setup_fee,
                    "trial_days": cint(plan.trial_days) if cint(plan.trial_enabled) else 0,
                    "renewal_mode": plan.renewal_mode,
                    "billing_cycles": cint(plan.billing_cycles),
                    "user_limit": cint(plan.user_limit),
                    "product_count": len(included),
                    "module_count": sum(p["module_count"] for p in included),
                    "products": included,
                    "excluded_products": excluded,
                    "is_current_plan": plan.name in current_plans,
                }
            )
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total else 0,
            },
        }