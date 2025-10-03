"""Config flow for Daily Fund."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_FUND_CODE,
    CONF_FUND_NAME,
    CONF_AVG_NET_VALUE,
    CONF_HOLD_SHARES,
    CONF_INITIAL_COST,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

class DailyFundConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Daily Fund."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate fund code (6 digits)
            fund_code = user_input[CONF_FUND_CODE]
            if len(fund_code) != 6 or not fund_code.isdigit():
                errors[CONF_FUND_CODE] = "invalid_fund_code"
            else:
                # Check if already configured
                await self.async_set_unique_id(fund_code)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_FUND_NAME],
                    data=user_input,
                )

        # 使用中文标签
        data_schema = vol.Schema({
            vol.Required(CONF_FUND_CODE): str,
            vol.Required(CONF_FUND_NAME): str,
            vol.Optional(CONF_AVG_NET_VALUE, default=0): vol.Coerce(float),
            vol.Optional(CONF_HOLD_SHARES, default=0): vol.Coerce(float),
            vol.Optional(CONF_INITIAL_COST, default=0): vol.Coerce(float),
            vol.Optional(
                CONF_UPDATE_INTERVAL, 
                default=DEFAULT_SCAN_INTERVAL
            ): vol.All(vol.Coerce(int), vol.Range(min=60)),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "fund_code": "基金代码 (6位数字)",
                "fund_name": "基金名称",
                "avg_net_value": "平均净值",
                "hold_shares": "持仓份额",
                "initial_cost": "初始成本",
                "update_interval": "更新间隔(秒)"
            }
        )