"""Sensor platform for Daily Fund."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import DailyFundCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Daily Fund sensor platform."""
    
    coordinator: DailyFundCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    # 每个基金只创建一个实体
    async_add_entities([DailyFundSensor(coordinator)], True)


class DailyFundSensor(SensorEntity):
    """Representation of a Daily Fund Sensor."""

    def __init__(self, coordinator: DailyFundCoordinator) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_name = coordinator.fund_name
        self._attr_unique_id = f"{coordinator.fund_code}_fund"
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.fund_code)},
            name=f"每日基金 - {coordinator.fund_name}",
            manufacturer="每日基金",
            model=coordinator.fund_code,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self):
        """Return the state of the sensor - 净值日期."""
        if self.coordinator.data is None:
            return None
            
        return self.coordinator.data.get("net_value_date")  # 显示净值日期

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return None

    @property
    def extra_state_attributes(self):
        """Return all fund data as attributes organized by categories."""
        if self.coordinator.data is None:
            return {}
            
        data = self.coordinator.data
            
        return {
            # 基础数据
            "基金代码": data.get("fund_code"),
            "基金名称": data.get("fund_name"),
            "基金全称": data.get("fund_full_name"),
            "涨跌净值": data.get("rise_fall_net_value"),  # 涨跌净值放在涨跌图标之前
            "涨跌图标": data.get("rise_fall_icon"),  # 涨跌图标
            "平均净值": data.get("avg_net_value"),
            "持仓份额": data.get("hold_shares"),
            "初始成本": data.get("initial_cost"),
            
            # 净值数据
            "净值日期": data.get("net_value_date"),
            "单位净值": data.get("actual_net_value"),
            "持仓市值": data.get("actual_value"),
            "持仓收益": data.get("actual_profit"),
            "持仓收益率": data.get("actual_profit_rate"),
            
            # 估算数据
            "估算时间": data.get("update_time"),
            "估算净值": data.get("estimated_net_value"),
            "估算增长率": data.get("estimated_growth_rate"),
            "估算市值": data.get("estimated_value"),
            "估算收益": data.get("estimated_profit"),
            "估算收益率": data.get("estimated_profit_rate"),
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(
                self.async_write_ha_state
            )
        )

    async def async_update(self) -> None:
        """Update the entity."""
        await self.coordinator.async_request_refresh()