# ---------------------------------------------------------------- doctypes
SUBSCRIPTION_DOCTYPE = "Custom Subscription"
SUB_MODULE_DOCTYPE = "Custom Subscription Module"  # child table of Custom Subscription
CUSTOMER_DOCTYPE = "Customer"  # ERPNext

SUB_MODULES_FIELD = "modules"  # child table fieldname on Custom Subscription
SUBSCRIPTION_SERIES = "SUB-.YYYY.-.####"  # SUB-2026-0001, counter restarts every year

# ---------------------------------------------------------------- status
# Status is NOT stored. It is worked out from the dates every time it is read, so it can never
# be stale and no scheduler / background job is needed.
STATUS_SCHEDULED = "Scheduled"  # start_date is in the future
STATUS_TRIALING = "Trialing"  # started, free trial still running
STATUS_ACTIVE = "Active"
STATUS_EXPIRED = "Expired"  # Fixed Cycles plan has finished
STATUS_CANCELLED = "Cancelled"
LIVE_STATUSES = (STATUS_SCHEDULED, STATUS_TRIALING, STATUS_ACTIVE)
ALL_STATUSES = LIVE_STATUSES + (STATUS_EXPIRED, STATUS_CANCELLED)

# ---------------------------------------------------------------- billing frequency
FREQUENCY_MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
BILLING_CUSTOM = "Custom"
SUBSCRIPTION_FREQUENCIES = tuple(FREQUENCY_MONTHS) + (BILLING_CUSTOM,)
MAX_CUSTOM_MONTHS = 120

# ---------------------------------------------------------------- limits
MAX_BACKDATE_DAYS = 31  # start_date may be at most this many days in the past
MAX_FUTURE_START_DAYS = 365
MAX_REASON_LENGTH = 500
MAX_NOTES_LENGTH = 5000
MAX_SHORT_TEXT = 140

# ---------------------------------------------------------------- list API
DEFAULT_PAGE = 1
MAX_PAGE = 100000
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
DEFAULT_SORT_BY = "modified"
DEFAULT_SORT_ORDER = "desc"
SORT_ORDERS = ("asc", "desc")
# status is derived (not a column) so it cannot be a sort field
ALLOWED_SORT_FIELDS = {"name", "creation", "modified", "customer_name", "start_date", "end_date", "grand_total"}

# ---------------------------------------------------------------- returned fields (real DB columns)
LIST_COLUMNS = [
    "name",
    "customer",
    "customer_name",
    "plan",
    "plan_name",
    "billing_frequency",
    "period_months",
    "currency",
    "subtotal",
    "discount_amount",
    "grand_total",
    "renewal_mode",
    "billing_cycles",
    "start_date",
    "trial_end_date",
    "end_date",
    "cancelled_on",
    "creation",
    "modified",
]

DETAIL_FIELDS = LIST_COLUMNS + [
    "plan_code",
    "pricing_model",
    "plan_billing_frequency",
    "custom_interval_months",
    "plan_price",
    "setup_fee",
    "discount_reason",
    "trial_enabled",
    "trial_days",
    "user_limit",
    "products",
    "cancel_reason",
    "notes",
    "request_id",
]

MODULE_ROW_FIELDS = ["name", "module", "module_name", "product", "price", "is_enabled"]

# ---------------------------------------------------------------- messages
MSG_NOT_FOUND = "Subscription '{sub_id}' not found"
MSG_STALE = "This subscription was changed by someone else, please reload and try again"