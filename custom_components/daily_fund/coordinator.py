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
        
        # 基金名称缓存
        self._fund_name_cache = None

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
            
            # 尝试多个API源
            fund_data = await self._fetch_fund_data()
            
            if not fund_data:
                raise UpdateFailed("无法获取基金数据")
            
            return self._process_fund_data(fund_data)
                    
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"网络请求错误: {err}")
        except Exception as err:
            raise UpdateFailed(f"未知错误: {err}")

    async def _fetch_fund_data(self) -> dict:
        """Fetch fund data from multiple API sources."""
        # API源列表（按优先级排序）
        api_sources = [
            self._fetch_from_eastmoney_api,
            self._fetch_from_eastmoney_pingzhong,
            self._fetch_from_sina_api,
        ]
        
        for api_func in api_sources:
            try:
                data = await api_func()
                if data:
                    _LOGGER.debug(f"成功从 {api_func.__name__} 获取数据")
                    return data
            except Exception as e:
                _LOGGER.warning(f"从 {api_func.__name__} 获取数据失败: {e}")
                continue
        
        return None

    async def _fetch_from_eastmoney_api(self) -> dict:
        """从天天基金网官方API获取数据."""
        url = f"https://api.fund.eastmoney.com/f10/lsjz"
        params = {
            "fundCode": self.fund_code,
            "pageIndex": 1,
            "pageSize": 1
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://fund.eastmoney.com/"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"API请求失败，状态码: {response.status}")
                
                text = await response.text()
                data = json.loads(text)
                
                if data.get("Data") and data["Data"].get("LSJZList"):
                    lsjz_list = data["Data"]["LSJZList"]
                    if lsjz_list:
                        fund_info = lsjz_list[0]
                        # 获取基金名称
                        fund_name = data.get("Data", {}).get("FundName", self.fund_name)
                        
                        return {
                            "fundcode": self.fund_code,
                            "name": fund_name,
                            "dwjz": fund_info.get("DWJZ", "0"),
                            "jzrq": fund_info.get("FSRQ", ""),
                            "gsz": fund_info.get("DWJZ", "0"),  # 使用历史净值作为估算
                            "gszzl": "0",
                            "gztime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
        
        return None

    async def _fetch_from_eastmoney_pingzhong(self) -> dict:
        """从天天基金网平中数据API获取数据."""
        url = f"https://fund.eastmoney.com/pingzhongdata/{self.fund_code}.js"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://fund.eastmoney.com/"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"API请求失败，状态码: {response.status}")
                
                text = await response.text()
                
                # 解析JavaScript中的数据
                fund_name = self._extract_js_value(text, "fS_name")
                dwjz = self._extract_js_value(text, "fS_dwjz")
                gsz = self._extract_js_value(text, "fS_gsz")
                gszzl = self._extract_js_value(text, "fS_gszzl")
                jzrq = self._extract_js_value(text, "fS_jzrq")
                gztime = self._extract_js_value(text, "fS_gztime")
                
                if fund_name or dwjz:
                    return {
                        "fundcode": self.fund_code,
                        "name": fund_name or self.fund_name,
                        "dwjz": dwjz or "0",
                        "jzrq": jzrq or "",
                        "gsz": gsz or dwjz or "0",
                        "gszzl": gszzl or "0",
                        "gztime": gztime or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
        
        return None

    async def _fetch_from_sina_api(self) -> dict:
        """从新浪财经API获取数据."""
        url = f"https://hq.sinajs.cn/list=f_{self.fund_code}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"API请求失败，状态码: {response.status}")
                
                text = await response.text()
                
                # 解析新浪格式数据
                # 格式: var hq_str_f_012889="基金名称,今日开盘价,昨收盘价,当前价格,最高价,最低价,...";
                if '="' in text:
                    data_str = text.split('="')[1].split('";')[0]
                    parts = data_str.split(',')
                    
                    if len(parts) >= 4:
                        fund_name = parts[0]
                        current_price = parts[3]  # 当前价格
                        yesterday_price = parts[2]  # 昨收盘价
                        
                        # 计算涨跌幅
                        try:
                            current = float(current_price)
                            yesterday = float(yesterday_price)
                            gszzl = ((current - yesterday) / yesterday * 100) if yesterday else 0
                        except:
                            gszzl = 0
                        
                        return {
                            "fundcode": self.fund_code,
                            "name": fund_name,
                            "dwjz": yesterday_price,  # 使用昨收盘作为单位净值
                            "jzrq": datetime.now().strftime("%Y-%m-%d"),
                            "gsz": current_price,  # 使用当前价格作为估算净值
                            "gszzl": str(gszzl),
                            "gztime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
        
        return None

    def _extract_js_value(self, text: str, key: str) -> str:
        """从JavaScript变量中提取值."""
        pattern = rf'{key}\s*=\s*"([^"]*)"'
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        
        pattern = rf'{key}\s*=\s*([^;]*);'
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            return value
        
        return ""

    def _process_fund_data(self, fund_data: dict) -> dict:
        """Process raw fund data."""
        try:
            gsz = self._parse_number(fund_data.get('gsz', 0))
            gszzl = self._parse_number(fund_data.get('gszzl', 0))
            dwjz = self._parse_number(fund_data.get('dwjz', 0))
        except (TypeError, ValueError) as e:
            _LOGGER.error("数值解析错误: %s, 数据: %s", e, fund_data)
            raise UpdateFailed(f"数值解析错误: {e}")
        
        # 获取基金全称
        fund_full_name = fund_data.get('name', self.fund_name)
        
        # 计算关键指标
        estimated_net_value = self._format_number(gsz, 4)
        estimated_growth_rate = self._format_number(gszzl, 4)
        estimated_value = self._format_number(self.hold_shares * gsz, 2)
        estimated_profit = self._format_number(estimated_value - self.initial_cost, 2)
        estimated_profit_rate = self._format_number(
            (estimated_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )
        
        actual_net_value = self._format_number(dwjz, 4)
        actual_value = self._format_number(self.hold_shares * dwjz, 2)
        actual_profit = self._format_number(actual_value - self.initial_cost, 2)
        actual_profit_rate = self._format_number(
            (actual_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )
        
        rise_fall_net_value = self._format_number(gsz - dwjz, 4)
        avg_net_value = self._format_number(self.avg_net_value, 4)
        
        net_value_date = fund_data.get('jzrq', '')
        update_time = fund_data.get('gztime', '')
        
        rise_fall_icon = "📈" if estimated_profit >= actual_profit else "📉"
        
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "fund_full_name": fund_full_name,
            "rise_fall_net_value": rise_fall_net_value,
            "rise_fall_icon": rise_fall_icon,
            "avg_net_value": avg_net_value,
            "hold_shares": self._format_number(self.hold_shares, 2),
            "initial_cost": self._format_number(self.initial_cost, 2),
            "net_value_date": net_value_date,
            "actual_net_value": actual_net_value,
            "actual_value": actual_value,
            "actual_profit": actual_profit,
            "actual_profit_rate": actual_profit_rate,
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
            
        try:
            cleaned = str(value).replace('%', '').replace(',', '')
            return float(cleaned)
        except (ValueError, TypeError):
            _LOGGER.warning("无法解析数值: %s", value)
            return 0

    def _format_number(self, value, decimals=2):
        """Format number with specified decimal places."""
        try:
            factor = 10 ** decimals
            return round(value * factor) / factor
        except (TypeError, ValueError):
            _LOGGER.warning("无法格式化数值: %s", value)
            return 0