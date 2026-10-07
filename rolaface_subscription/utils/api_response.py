import frappe
from frappe.utils import strip_html

GENERIC_ERROR_MESSAGE = "Unable to process your request, please try again later"
NO_PERMISSION_MESSAGE = "You do not have permission to perform this action."
DUPLICATE_MESSAGE = "A record with the same unique value already exists"
RETRY_MESSAGE = "The system is busy, please retry in a moment"
STALE_MESSAGE = "This record was changed by someone else, please reload and try again"

_RETRYABLE = tuple(
    c for c in (getattr(frappe, "QueryDeadlockError", None), getattr(frappe, "QueryTimeoutError", None)) if c
)


class ConflictError(frappe.ValidationError):
    http_status_code = 409


class CustomerSyncError(frappe.ValidationError):
    """The customer site rejected or could not be reached for a sync call."""
    http_status_code = 502


def _respond(status, message, status_code, data=None, pagination=None):
    payload = {"status_code": status_code, "status": status, "message": message}
    if data is not None:
        payload["data"] = data
    if pagination is not None:
        payload["pagination"] = pagination

    frappe.local.response = frappe._dict(payload)
    frappe.local.response["http_status_code"] = status_code


def send_response(message="", data=None, status="success", status_code=200):
    _respond(status, message, status_code, data=data)


def send_response_list(message="", data=None, pagination=None, status="success", status_code=200):
    _respond(
        status,
        message,
        status_code,
        data=data if data is not None else [],
        pagination=pagination,
    )


def _log_unexpected_error(context_message: str) -> None:
    try:
        frappe.log_error(title=context_message, message=frappe.get_traceback())
        frappe.db.commit()
    except Exception:
        pass


def handle_api_error(e: Exception, context_message: str = "API request failed"):
    frappe.db.rollback()
    frappe.clear_messages()

    status, message = "fail", strip_html(str(e)).strip()


    if isinstance(e, frappe.DoesNotExistError):
        status_code = 404
    elif isinstance(e, frappe.DuplicateEntryError):
        status_code, message = 409, DUPLICATE_MESSAGE
    elif isinstance(e, frappe.UniqueValidationError):
        status_code = 409
        message = message or DUPLICATE_MESSAGE
    elif isinstance(e, frappe.TimestampMismatchError):
        status_code, message = 409, STALE_MESSAGE
    elif isinstance(e, ConflictError):
        status_code = 409
    elif isinstance(e, frappe.PermissionError):
        status_code, message = 403, NO_PERMISSION_MESSAGE
    elif isinstance(e, frappe.ValidationError):
        status_code = 400
    elif _RETRYABLE and isinstance(e, _RETRYABLE):
        status, status_code, message = "error", 503, RETRY_MESSAGE
    else:
        status, status_code = "error", 500
        _log_unexpected_error(context_message)
        message = f"{type(e).__name__}: {e}" if frappe.conf.developer_mode else GENERIC_ERROR_MESSAGE

    _respond(status, message or GENERIC_ERROR_MESSAGE, status_code)