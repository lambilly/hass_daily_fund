"""Constants for Daily Fund integration."""

DOMAIN = "daily_fund"
DEFAULT_NAME = "每日基金"
DEFAULT_SCAN_INTERVAL = 600  # 10 minutes

CONF_FUND_CODE = "fund_code"
CONF_FUND_NAME = "fund_name"
CONF_AVG_NET_VALUE = "avg_net_value"
CONF_HOLD_SHARES = "hold_shares"
CONF_INITIAL_COST = "initial_cost"
CONF_UPDATE_INTERVAL = "update_interval"

API_URL_TEMPLATE = "https://fundgz.1234567.com.cn/js/{}.js"