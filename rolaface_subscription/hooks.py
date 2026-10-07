app_name = "rolaface_subscription"
app_title = "Rolaface Subscription"
app_publisher = "Rolaface"
app_description = "Custom subscription management for Rolaface"
app_email = "shivangi.sharma@rolaface.com"
app_license = "apache-2.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "rolaface_subscription",
# 		"logo": "/assets/rolaface_subscription/logo.png",
# 		"title": "Rolaface Subscription",
# 		"route": "/rolaface_subscription",
# 		"has_permission": "rolaface_subscription.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/rolaface_subscription/css/rolaface_subscription.css"
# app_include_js = "/assets/rolaface_subscription/js/rolaface_subscription.js"

# include js, css files in header of web template
# web_include_css = "/assets/rolaface_subscription/css/rolaface_subscription.css"
# web_include_js = "/assets/rolaface_subscription/js/rolaface_subscription.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "rolaface_subscription/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "rolaface_subscription/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rolaface_subscription.utils.jinja_methods",
# 	"filters": "rolaface_subscription.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rolaface_subscription.install.before_install"
after_install = "rolaface_subscription.seeders.run_all_seeders"
after_migrate = "rolaface_subscription.seeders.run_all_seeders"

# Uninstallation
# ------------

# before_uninstall = "rolaface_subscription.uninstall.before_uninstall"
# after_uninstall = "rolaface_subscription.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "rolaface_subscription.utils.before_app_install"
# after_app_install = "rolaface_subscription.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "rolaface_subscription.utils.before_app_uninstall"
# after_app_uninstall = "rolaface_subscription.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "rolaface_subscription.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rolaface_subscription.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"rolaface_subscription.modules.subscription.tasks.refresh_subscription_statuses",
	],
}

# scheduler_events = {
# 	"all": [
# 		"rolaface_subscription.tasks.all"
# 	],
# 	"daily": [
# 		"rolaface_subscription.tasks.daily"
# 	],
# 	"hourly": [
# 		"rolaface_subscription.tasks.hourly"
# 	],
# 	"weekly": [
# 		"rolaface_subscription.tasks.weekly"
# 	],
# 	"monthly": [
# 		"rolaface_subscription.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "rolaface_subscription.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "rolaface_subscription.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rolaface_subscription.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rolaface_subscription.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["rolaface_subscription.utils.before_request"]
# after_request = ["rolaface_subscription.utils.after_request"]

# Job Events
# ----------
# before_job = ["rolaface_subscription.utils.before_job"]
# after_job = ["rolaface_subscription.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rolaface_subscription.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

