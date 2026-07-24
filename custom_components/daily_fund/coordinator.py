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
        am_start = time(TRADING_HOURS_AM_START, TRADING_HOURS_AM_START_MINUTE)
        am_end = time(TRADING_HOURS_AM_END, TRADING_HOURS_AM_END_MINUTE)
        pm_start = time(TRADING_HOURS_PM_START, 0)
        pm_end = time(TRADING_HOURS_PM_END, 0)
        return (am_start <= current_time <= am_end) or (pm_start <= current_time <= pm_end)

    def _is_net_value_publish_hours(self, current_time: time) -> bool:
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
            
            fund_data = await self._fetch_fund_data()
            
            if not fund_data:
                raise UpdateFailed("无法获取基金数据")
            
            return self._process_fund_data(fund_data)
                    
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"网络请求错误: {err}")
        except Exception as err:
            raise UpdateFailed(f"未知错误: {err}")

    async def _fetch_fund_data(self) -> dict:
        """
        获取基金数据，合并多个API源：
        1. 先从历史净值API获取基础数据（含前天），保证前天数据。
        2. 再从fundgz获取实时估算数据（gsz, gszzl, gztime），覆盖估算字段。
        3. 如果fundgz失败，则使用历史净值的净值作为估算。
        4. 如果历史净值失败，尝试其他源（平中数据）作为备用。
        """
        base_data = None
        estimate_data = None

        # 第一步：获取历史净值（含前天）
        try:
            base_data = await self._fetch_from_eastmoney_api()
            if base_data:
                _LOGGER.debug("成功获取历史净值数据（含前天）")
        except Exception as e:
            _LOGGER.warning("获取历史净值失败: %s", e)

        # 第二步：获取实时估算（如果历史净值成功，则用估算覆盖；如果历史净值失败，则尝试单独获取估算）
        try:
            estimate_data = await self._fetch_from_fundgz()
            if estimate_data:
                _LOGGER.debug("成功获取实时估算数据")
        except Exception as e:
            _LOGGER.warning("获取实时估算失败: %s", e)

        # 合并数据
        if base_data:
            # 用估算数据覆盖相关字段
            if estimate_data:
                base_data["gsz"] = estimate_data.get("gsz", base_data.get("dwjz", "0"))
                base_data["gszzl"] = estimate_data.get("gszzl", "0")
                base_data["gztime"] = estimate_data.get("gztime", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                # 无估算，使用历史净值作为估算
                base_data["gsz"] = base_data.get("dwjz", "0")
                base_data["gszzl"] = "0"
                base_data["gztime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return base_data

        # 如果历史净值失败，尝试其他源（fundgz或平中）
        if estimate_data:
            # 仅估算数据（无前天信息）
            estimate_data["prev_dwjz"] = "0"
            estimate_data["prev_jzrq"] = ""
            return estimate_data

        # 最后尝试平中数据
        try:
            pingzhong_data = await self._fetch_from_eastmoney_pingzhong()
            if pingzhong_data:
                pingzhong_data["prev_dwjz"] = "0"
                pingzhong_data["prev_jzrq"] = ""
                return pingzhong_data
        except Exception as e:
            _LOGGER.warning("获取平中数据失败: %s", e)

        return None

    # ---------- API源1：历史净值（含前天） ----------
    async def _fetch_from_eastmoney_api(self) -> dict:
        """从天天基金网官方API获取历史净值（最近两条，用于前天净值）."""
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        params = {
            "fundCode": self.fund_code,
            "pageIndex": 1,
            "pageSize": 2,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://fund.eastmoney.com/"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                text = await response.text()
                data = json.loads(text)
                
                if data.get("Data") and data["Data"].get("LSJZList"):
                    lsjz_list = data["Data"]["LSJZList"]
                    if not lsjz_list:
                        raise Exception("无历史净值")
                    
                    latest = lsjz_list[0]
                    prev = lsjz_list[1] if len(lsjz_list) > 1 else None
                    fund_name = data["Data"].get("FundName", self.fund_name)
                    
                    return {
                        "fundcode": self.fund_code,
                        "name": fund_name,
                        "dwjz": latest.get("DWJZ", "0"),
                        "jzrq": latest.get("FSRQ", ""),
                        "prev_dwjz": prev.get("DWJZ", "0") if prev else "0",
                        "prev_jzrq": prev.get("FSRQ", "") if prev else "",
                        # 估算字段占位，后续会被覆盖
                        "gsz": "0",
                        "gszzl": "0",
                        "gztime": "",
                    }
                raise Exception("无法解析历史净值")

    # ---------- API源2：fundgz（实时估算） ----------
    async def _fetch_from_fundgz(self) -> dict:
        """从天天基金 fundgz 接口获取实时估算数据."""
        url = f"http://fundgz.1234567.com.cn/js/{self.fund_code}.js"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://fund.eastmoney.com/"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                text = await response.text()
                text = text.strip()
                if not text:
                    raise Exception("空响应")
                
                # 处理 JSONP
                if text.startswith('jsonpgz(') and text.endswith(');'):
                    json_str = text[8:-2]
                else:
                    json_str = text
                
                data = json.loads(json_str)
                
                if not data.get('fundcode'):
                    raise Exception("缺少 fundcode")
                
                return {
                    "fundcode": self.fund_code,
                    "name": data.get('name', self.fund_name),
                    "dwjz": data.get('dwjz', '0'),   # 也可提供，但不一定是最新
                    "jzrq": data.get('jzrq', ''),
                    "gsz": data.get('gsz', '0'),
                    "gszzl": data.get('gszzl', '0'),
                    "gztime": data.get('gztime', ''),
                    # 不提供前天数据
                    "prev_dwjz": "0",
                    "prev_jzrq": "",
                }

    # ---------- API源3：平中数据（备用实时估算） ----------
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
                    raise Exception(f"HTTP {response.status}")
                text = await response.text()
                
                fund_name = self._extract_js_value(text, "fS_name")
                dwjz = self._extract_js_value(text, "fS_dwjz")
                gsz = self._extract_js_value(text, "fS_gsz")
                gszzl = self._extract_js_value(text, "fS_gszzl")
                jzrq = self._extract_js_value(text, "fS_jzrq")
                gztime = self._extract_js_value(text, "fS_gztime")
                
                if not dwjz and not gsz:
                    raise Exception("未提取到净值数据")
                
                return {
                    "fundcode": self.fund_code,
                    "name": fund_name or self.fund_name,
                    "dwjz": dwjz or "0",
                    "jzrq": jzrq or "",
                    "gsz": gsz or dwjz or "0",
                    "gszzl": gszzl or "0",
                    "gztime": gztime or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "prev_dwjz": "0",
                    "prev_jzrq": "",
                }

    # ---------- 辅助方法 ----------
    def _extract_js_value(self, text: str, key: str) -> str:
        """从JavaScript代码中提取变量值（支持多种格式）."""
        patterns = [
            rf'{key}\s*=\s*"([^"]*)"',
            rf'{key}\s*=\s*\'([^\']*)\'',
            rf'{key}\s*=\s*([^;]*);',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
        return ""

    def _process_fund_data(self, fund_data: dict) -> dict:
        """处理基金数据，计算各项指标."""
        try:
            gsz = self._parse_number(fund_data.get('gsz', 0))
            gszzl = self._parse_number(fund_data.get('gszzl', 0))
            dwjz = self._parse_number(fund_data.get('dwjz', 0))
            prev_dwjz = self._parse_number(fund_data.get('prev_dwjz', 0))
            prev_jzrq = fund_data.get('prev_jzrq', '')
        except Exception as e:
            _LOGGER.error("数值解析错误: %s", e)
            raise UpdateFailed(f"数值解析错误: {e}")

        # 如果估算净值为0，使用单位净值代替
        if gsz == 0 and dwjz > 0:
            gsz = dwjz

        # 如果前天净值为0，则无法计算前天相关指标，设为0
        if prev_dwjz <= 0:
            prev_net_value = 0
            prev_value = 0
            prev_profit = 0
            prev_profit_rate = 0
            prev_growth_rate = 0
            # 涨跌净值也无法计算，使用0
            rise_fall_net_value = 0
        else:
            prev_net_value = self._format_number(prev_dwjz, 4)
            # 前天市值
            prev_value = self._format_number(self.hold_shares * prev_dwjz, 2)
            # 前天收益（相对于初始成本）
            prev_profit = self._format_number(prev_value - self.initial_cost, 2)
            # 前天收益率
            prev_profit_rate = self._format_number(
                (prev_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
            )
            # 前天增长率（前天到昨天的增长率） = (dwjz - prev_dwjz) / prev_dwjz * 100
            prev_growth_rate = self._format_number(
                (dwjz - prev_dwjz) / prev_dwjz * 100, 4
            )
            # 涨跌净值 = 单位净值 - 前天净值
            rise_fall_net_value = self._format_number(dwjz - prev_dwjz, 4)

        fund_full_name = fund_data.get('name', self.fund_name)

        # 估算指标
        estimated_net_value = self._format_number(gsz, 4)
        estimated_growth_rate = self._format_number(gszzl, 4)
        estimated_value = self._format_number(self.hold_shares * gsz, 2)
        estimated_profit = self._format_number(estimated_value - self.initial_cost, 2)
        estimated_profit_rate = self._format_number(
            (estimated_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )

        # 实际（昨天）指标
        actual_net_value = self._format_number(dwjz, 4)
        actual_value = self._format_number(self.hold_shares * dwjz, 2)
        actual_profit = self._format_number(actual_value - self.initial_cost, 2)
        actual_profit_rate = self._format_number(
            (actual_profit / self.initial_cost * 100) if self.initial_cost else 0, 2
        )

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
            # 前天相关
            "prev_net_value": prev_net_value,
            "prev_net_value_date": prev_jzrq,      # 将作为“前天日期”
            "prev_value": prev_value,
            "prev_profit": prev_profit,
            "prev_profit_rate": prev_profit_rate,
            "prev_growth_rate": prev_growth_rate,
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
            return 0