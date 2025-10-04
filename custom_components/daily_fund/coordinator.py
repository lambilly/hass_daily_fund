"""Coordinator for Daily Fund integration."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime, time
import aiohttp
import json
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_FUND_CODE,
    CONF_FUND_NAME,
    CONF_AVG_NET_VALUE,
    CONF_HOLD_SHARES,
    CONF_INITIAL_COST,
    CONF_TRADING_INTERVAL,
    CONF_NET_VALUE_INTERVAL,
    DEFAULT_TRADING_INTERVAL,
    DEFAULT_NET_VALUE_INTERVAL,
    DEFAULT_NON_TRADING_INTERVAL,
    TRADING_HOURS_AM_START,
    TRADING_HOURS_AM_START_MINUTE,
    TRADING_HOURS_AM_END,
    TRADING_HOURS_AM_END_MINUTE,
    TRADING_HOURS_PM_START,
    TRADING_HOURS_PM_END,
    NET_VALUE_PUBLISH_START,
    NET_VALUE_PUBLISH_END,
    API_URL_TEMPLATE
)

_LOGGER = logging.getLogger(__name__)

class DailyFundCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Daily Fund data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        # 获取智能更新间隔配置
        self.trading_interval = entry.data.get(CONF_TRADING_INTERVAL, DEFAULT_TRADING_INTERVAL)
        self.net_value_interval = entry.data.get(CONF_NET_VALUE_INTERVAL, DEFAULT_NET_VALUE_INTERVAL)
        self.non_trading_interval = DEFAULT_NON_TRADING_INTERVAL
        
        # 初始使用默认间隔
        initial_interval = self._calculate_optimal_interval()
        
        super().__init__(
            hass,
            _LOGGER,
            name=entry.data[CONF_FUND_NAME],
            update_interval=timedelta(seconds=initial_interval),
        )
        
        self.entry = entry
        self.fund_code = entry.data[CONF_FUND_CODE]
        self.fund_name = entry.data[CONF_FUND_NAME]
        self.avg_net_value = float(entry.data.get(CONF_AVG_NET_VALUE, 0))
        self.hold_shares = float(entry.data.get(CONF_HOLD_SHARES, 0))
        self.initial_cost = float(entry.data.get(CONF_INITIAL_COST, 0))

    def _calculate_optimal_interval(self) -> int:
        """Calculate optimal update interval based on current time."""
        now = datetime.now()
        current_time = now.time()
        
        # 检查是否在交易时段内
        is_trading_hours = self._is_trading_hours(current_time)
        
        # 检查是否在净值公布时段内
        is_net_value_publish_hours = self._is_net_value_publish_hours(current_time)
        
        # 确定更新间隔
        if is_trading_hours:
            return self.trading_interval
        elif is_net_value_publish_hours:
            return self.net_value_interval
        else:
            return self.non_trading_interval

    def _is_trading_hours(self, current_time: time) -> bool:
        """Check if current time is within trading hours."""
        # 上午交易时段: 9:30 - 11:30
        am_start = time(TRADING_HOURS_AM_START, TRADING_HOURS_AM_START_MINUTE)
        am_end = time(TRADING_HOURS_AM_END, TRADING_HOURS_AM_END_MINUTE)
        
        # 下午交易时段: 13:00 - 15:00
        pm_start = time(TRADING_HOURS_PM_START, 0)
        pm_end = time(TRADING_HOURS_PM_END, 0)
        
        return (am_start <= current_time <= am_end) or (pm_start <= current_time <= pm_end)

    def _is_net_value_publish_hours(self, current_time: time) -> bool:
        """Check if current time is within net value publish hours."""
        publish_start = time(NET_VALUE_PUBLISH_START, 0)
        publish_end = time(NET_VALUE_PUBLISH_END, 0)
        
        return publish_start <= current_time <= publish_end

    async def _async_update_data(self):
        """Update data via API."""
        try:
            # 在每次更新前重新计算最优间隔
            new_interval = self._calculate_optimal_interval()
            if self.update_interval != timedelta(seconds=new_interval):
                self.update_interval = timedelta(seconds=new_interval)
                _LOGGER.debug(
                    "Updated refresh interval to %s seconds for fund %s",
                    new_interval,
                    self.fund_code
                )
            
            async with aiohttp.ClientSession() as session:
                url = API_URL_TEMPLATE.format(self.fund_code)
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"API请求失败，状态码: {response.status}")
                    
                    text = await response.text()
                    
                    # Remove JSONP wrapper
                    json_str = re.sub(r'^jsonpgz\(|\);$', '', text)
                    fund_data = json.loads(json_str)
                    
                    return self._process_fund_data(fund_data)
                    
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"网络请求错误: {err}")
        except json.JSONDecodeError as err:
            raise UpdateFailed(f"数据解析错误: {err}")
        except Exception as err:
            raise UpdateFailed(f"未知错误: {err}")

    def _process_fund_data(self, fund_data: dict) -> dict:
        """Process raw fund data."""
        # Parse values
        gsz = self._parse_number(fund_data.get('gsz', 0))  # 估算净值
        gszzl = self._parse_number(fund_data.get('gszzl', 0))  # 估算增长率
        dwjz = self._parse_number(fund_data.get('dwjz', 0))  # 单位净值
        
        # 获取基金全称
        fund_full_name = fund_data.get('name', self.fund_name)
        
        # 计算关键指标
        # 估算数据
        estimated_net_value = self._format_number(gsz, 4)  # 保留4位小数
        estimated_growth_rate = self._format_number(gszzl, 4)  # 保留4位小数
        estimated_value = self._format_number(self.hold_shares * gsz, 2)  # 估算市值
        estimated_profit = self._format_number(estimated_value - self.initial_cost, 2)  # 估算收益
        estimated_profit_rate = self._format_number(
            (estimated_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )  # 估算收益率
        
        # 实际数据
        actual_net_value = self._format_number(dwjz, 4)  # 单位净值，保留4位小数
        actual_value = self._format_number(self.hold_shares * dwjz, 2)  # 持仓市值
        actual_profit = self._format_number(actual_value - self.initial_cost, 2)  # 持仓收益
        actual_profit_rate = self._format_number(
            (actual_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )  # 持仓收益率
        
        # 涨跌净值 - 保留4位小数
        rise_fall_net_value = self._format_number(gsz - dwjz, 4)
        
        # 平均净值 - 保留4位小数
        avg_net_value = self._format_number(self.avg_net_value, 4)
        
        # 净值日期和估算时间
        net_value_date = fund_data.get('jzrq', '')
        update_time = fund_data.get('gztime', '')
        
        # 计算涨跌图标 - 比较持仓收益和估算收益
        rise_fall_icon = "📈" if estimated_profit >= actual_profit else "📉"
        
        return {
            # 基础数据
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "fund_full_name": fund_full_name,  # 基金全称
            "rise_fall_net_value": rise_fall_net_value,  # 涨跌净值，放在涨跌图标之前
            "rise_fall_icon": rise_fall_icon,  # 涨跌图标
            "avg_net_value": avg_net_value,
            "hold_shares": self._format_number(self.hold_shares, 2),
            "initial_cost": self._format_number(self.initial_cost, 2),
            
            # 净值数据
            "net_value_date": net_value_date,
            "actual_net_value": actual_net_value,
            "actual_value": actual_value,
            "actual_profit": actual_profit,
            "actual_profit_rate": actual_profit_rate,
            
            # 估算数据
            "update_time": update_time,
            "estimated_net_value": estimated_net_value,
            "estimated_growth_rate": estimated_growth_rate,
            "estimated_value": estimated_value,
            "estimated_profit": estimated_profit,
            "estimated_profit_rate": estimated_profit_rate,
        }

    def _parse_number(self, value):
        """Parse number from string, handling percentages and commas."""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return value
            
        cleaned = str(value).replace('%', '').replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            return 0

    def _format_number(self, value, decimals=2):
        """Format number with specified decimal places."""
        factor = 10 ** decimals
        return round(value * factor) / factor