import frappe

from rolaface_subscription.modules.plan.service import PlanService
from rolaface_subscription.modules.plan.utils import (
    validate_create_payload,
    validate_get_by_id_params,
    validate_list_params,
    validate_status_payload,
    validate_update_payload,
)
from rolaface_subscription.utils.api_response import (
    handle_api_error,
    send_response,
    send_response_list,
)


@frappe.whitelist(allow_guest=False, methods=["POST"])
def create(**payload):
    try:
        data = validate_create_payload(payload)
        result = PlanService.create_plan(data)
        return send_response(message="Plan created successfully", data=result, status_code=201)
    except Exception as e:
        return handle_api_error(e, "Custom Plan create API failed")


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get(**params):
    try:
        data = validate_list_params(params)
        result = PlanService.get_plans(data)
        return send_response_list(
            message="Plans fetched successfully",
            data=result["items"],
            pagination=result["pagination"],
        )
    except Exception as e:
        return handle_api_error(e, "Custom Plan list API failed")


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_by_id(**params):
    try:
        data = validate_get_by_id_params(params)
        result = PlanService.get_plan(data["id"])
        return send_response(message="Plan fetched successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Plan get_by_id API failed")


@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update(**payload):
    try:
        # only the fields the client really sent are returned by the validator
        data = validate_update_payload(payload)
        result = PlanService.update_plan(data)
        return send_response(message="Plan updated successfully", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Plan update API failed")


@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update_status(**payload):
    try:
        data = validate_status_payload(payload)
        result = PlanService.update_plan_status(data)
        return send_response(message=f"Plan status changed to {data['status']}", data=result)
    except Exception as e:
        return handle_api_error(e, "Custom Plan update_status API failed")