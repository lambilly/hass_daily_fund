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

# 智能更新策略常量
CONF_TRADING_INTERVAL = "trading_interval"  # 交易时段更新间隔
CONF_NET_VALUE_INTERVAL = "net_value_interval"  # 净值公布时段更新间隔
DEFAULT_TRADING_INTERVAL = 300  # 交易时段默认5分钟
DEFAULT_NET_VALUE_INTERVAL = 900  # 净值公布时段默认15分钟
DEFAULT_NON_TRADING_INTERVAL = 3600  # 非交易时段默认1小时

# 交易时间设置
TRADING_HOURS_AM_START = 9
TRADING_HOURS_AM_START_MINUTE = 30
TRADING_HOURS_AM_END = 11
TRADING_HOURS_AM_END_MINUTE = 30
TRADING_HOURS_PM_START = 13
TRADING_HOURS_PM_END = 15

# 净值公布时段
NET_VALUE_PUBLISH_START = 18  # 18:00开始
NET_VALUE_PUBLISH_END = 22    # 22:00结束

API_URL_TEMPLATE = "https://fundgz.1234567.com.cn/js/{}.js"