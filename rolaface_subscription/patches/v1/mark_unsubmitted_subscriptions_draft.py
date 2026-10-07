from rolaface_subscription.modules.subscription.tasks import refresh_subscription_statuses

def execute():
    refresh_subscription_statuses()
