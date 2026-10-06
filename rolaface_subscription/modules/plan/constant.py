from decimal import Decimal

PLAN_DOCTYPE = "Custom Plan"
MODULE_DOCTYPE = "Custom Module"
PRODUCT_DOCTYPE = "Custom Product"
CURRENCY_DOCTYPE = "Currency"
PLAN_MODULE_DOCTYPE = "Custom Plan Module"

PLAN_MODULES_FIELD = "modules"  

CHILD_ROW_NAME_FIELD = {"name"}

ALLOWED_PLAN_FIELDS = {
    "plan_name",
    "plan_code",
    "user_limit",
    "status",
    "products",
    "description",
    "billing_frequency",
    "pricing_model",
    "currency",
    "base_price",
    "setup_fee",
    "trial_enabled",
    "trial_days",
    "renewal_mode",
    "billing_cycles",
}

PLAN_MODULE_FIELDS = CHILD_ROW_NAME_FIELD | {"module", "module_name", "product", "price", "currency"}

PLAN_UPDATABLE_FIELDS = {
    "plan_name",
    "user_limit",
    "description",
    "billing_frequency",
    "pricing_model",
    "currency",
    "base_price",
    "setup_fee",
    "trial_enabled",
    "trial_days",
    "renewal_mode",
    "billing_cycles",
}

PLAN_EDITABLE_STATUS = "Draft"  # only Draft plans can be edited
PLAN_ACTIVE_STATUS = "Active"
PLAN_INACTIVE_STATUS = "Inactive"
PLAN_STATUS_TRANSITIONS = {
    "Draft": ("Active",),
    "Active": ("Inactive",),
    "Inactive": ("Active",),
}

ALLOWED_SORT_FIELDS = {
    "name",
    "creation",
    "modified",
    "plan_name",
    "plan_code",
    "status",
    "billing_frequency",
    "base_price",
}

RETURN_FIELDS_GET_ALL = [
    "name",
    "plan_name",
    "plan_code",
    "status",
    "products",
    "pricing_model",
    "billing_frequency",
    "currency",
    "base_price",
    "creation",
]

RETURN_FIELDS_GET_BY_ID = list(ALLOWED_PLAN_FIELDS) + ["name", "creation", "modified", "docstatus"]


PLAN_STATUSES = ("Draft", "Active", "Inactive")
DEFAULT_STATUS = "Draft" 

BILLING_FREQUENCIES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")

PRICING_FLAT = "Flat"
PRICING_PER_MODULE = "Per Module"
PRICING_MODELS = (PRICING_FLAT, PRICING_PER_MODULE)

RENEWAL_AUTO = "Auto-renew"
RENEWAL_FIXED = "Fixed Cycles"
RENEWAL_MODES = (RENEWAL_AUTO, RENEWAL_FIXED)


MAX_USER_LIMIT = 1_000_000
MAX_TRIAL_DAYS = 3650
MAX_BILLING_CYCLES = 1200 
MAX_MODULES_PER_PLAN = 200

MAX_VARCHAR = 140  
MAX_NAME_LENGTH = 140
MAX_PLAN_CODE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000
MAX_AUTO_CODE_TRIES = 100


PRICE_DECIMAL_PLACES = 2
MAX_PRICE = Decimal("99999999.99")


DEFAULT_PAGE = 1
MAX_PAGE = 100000
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
DEFAULT_SORT_BY = "modified"
DEFAULT_SORT_ORDER = "desc"
SORT_ORDERS = ("asc", "desc")

MSG_PLAN_NOT_FOUND = "Plan '{plan_id}' not found"
MSG_STALE = "This plan was changed by someone else, please reload and try again"