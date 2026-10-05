import frappe

from rolaface_subscription.modules.subscription.service import SubscriptionService
from rolaface_subscription.modules.subscription.utils import (
    validate_cancel_payload,
    validate_create_payload,
    validate_entitlement_params,
    validate_get_by_id_params,
    validate_list_params,
    validate_update_payload,
)
from rolaface_subscription.utils.api_response import (
    handle_api_error,
    send_response,
    send_response_list,
)

# No role / permission checks (as decided). allow_guest=False only blocks Guest.


@frappe.whitelist(allow_guest=False, methods=["POST"])
def create(**payload):
    try:
        data = validate_create_payload(payload)
        result = SubscriptionService.create_subscription(data)
        if result.get("idempotent_replay"):
            return send_response(message="Subscription already created for this request_id", data=result)
        return send_response(message="Subscription created successfully", data=result, status_code=201)
    except Exception as e:
        return handle_api_error(e, "Custom Subscription create API failed")


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get(**params):
    try:
        data = validate_list_params(params)
        result = SubscriptionService.get_subscriptions(data)
        return send_response_list(
            message="Subscriptions fetched successfully",
            data=result["items"],
            pagination=result["pagination"],
        )
    except Exception as e:
        return handle_api_error(e, "Custom Subscription list API failed")


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_by_id(**params):
    try:
        data = validate_get_by_id_params(params)
        result = SubscriptionService.get_subscription(data["id"])
        return send_response(message="Subscription fetched successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Subscription get_by_id API failed")


@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update(**payload):
    try:
        data = validate_update_payload(payload)
        result = SubscriptionService.update_subscription(data)
        return send_response(message="Subscription updated successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Subscription update API failed")


@frappe.whitelist(allow_guest=False, methods=["PUT"])
def cancel(**payload):
    try:
        data = validate_cancel_payload(payload)
        result = SubscriptionService.cancel_subscription(data)
        return send_response(message="Subscription cancelled successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Subscription cancel API failed")


@frappe.whitelist(allow_guest=False, methods=["GET"])
def entitlements(**params):
    try:
        data = validate_entitlement_params(params)
        result = SubscriptionService.get_entitlements(data["customer"])
        return send_response(message="Entitlements fetched successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Subscription entitlements API failed")