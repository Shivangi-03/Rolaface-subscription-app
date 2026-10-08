SUBSCRIPTION_DOCTYPE = "Custom Subscription"
SUB_MODULE_DOCTYPE = "Custom Subscription Module"  
CUSTOMER_DOCTYPE = "Customer" 

SUB_MODULES_FIELD = "modules" 
SUBSCRIPTION_SERIES = "SUB-.YYYY.-.####"


STATUS_DRAFT = "Draft"
STATUS_SCHEDULED = "Scheduled"
STATUS_TRIALING = "Trialing"  
STATUS_ACTIVE = "Active"
STATUS_EXPIRED = "Expired"  
STATUS_CANCELLED = "Cancelled"
LIVE_STATUSES = (STATUS_SCHEDULED, STATUS_TRIALING, STATUS_ACTIVE)
ACCESS_STATUSES = (STATUS_TRIALING, STATUS_ACTIVE)
ENDED_STATUSES = (STATUS_EXPIRED, STATUS_CANCELLED)
OPEN_STATUSES = (STATUS_DRAFT,) + LIVE_STATUSES
ALL_STATUSES = OPEN_STATUSES + ENDED_STATUSES

FREQUENCY_MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
BILLING_CUSTOM = "Custom"
SUBSCRIPTION_FREQUENCIES = tuple(FREQUENCY_MONTHS) + (BILLING_CUSTOM,)
MAX_CUSTOM_MONTHS = 120

MAX_BACKDATE_DAYS = 31
MAX_FUTURE_START_DAYS = 365
MAX_REASON_LENGTH = 500
MAX_NOTES_LENGTH = 5000


DEFAULT_PAGE = 1
MAX_PAGE = 100000
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
DEFAULT_SORT_BY = "modified"
DEFAULT_SORT_ORDER = "desc"
SORT_ORDERS = ("asc", "desc")
ALLOWED_SORT_FIELDS = {"name", "creation", "modified", "customer_name", "start_date", "end_date", "grand_total"}

LIST_COLUMNS = [
    "name",
    "status",
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
    "trial_enabled",
    "trial_days",
    "user_limit",
    "products",
    "cancel_reason",
    "notes",
    "auto_sync",
]
UPDATABLE_FIELDS = ("plan", "start_date", "end_date", "discount_amount", "notes", "auto_sync")
UPDATE_CONTROL_KEYS = ("id", "modified", "cmd")
UPDATE_REJECT_UNKNOWN = True  

MODULE_ROW_FIELDS = ["name", "module", "module_name", "product", "price", "is_enabled"]

MSG_NOT_FOUND = "Subscription '{sub_id}' not found"
MSG_STALE = "This subscription was changed by someone else, please reload and try again"

# customer site sync: the backend URL of the customer's own site is stored in Customer.website
CUSTOMER_BACKEND_URL_FIELD = "website"

CUSTOMER_SYNC_CREATE_PATH = "/api/method/auth_api.module.subscription.api.create"
CUSTOMER_SYNC_DELETE_PATH = "/api/method/auth_api.module.subscription.api.delete"