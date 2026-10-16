"""Repair flows: pick a Gotway/Begode model, fix an InMotion V1 password."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .config_flow import (
    gotway_option_fields,
    gotway_options_from_input,
    password_defaults,
    password_schema_fields,
    resolve_password,
)
from .const import CONF_INMOTION_PASSWORD, ISSUE_GOTWAY_MODEL, ISSUE_INMOTION_PASSWORD


class _EntryRepairFlow(RepairsFlow):
    """Repair flow bound to one wheel config entry."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    def _entry(self):
        return self.hass.config_entries.async_get_entry(self._entry_id)


class GotwayModelRepairFlow(_EntryRepairFlow):
    """Select the Gotway/Begode model (sets the same option as the options flow)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_select_model()

    async def async_step_select_model(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_removed")
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, **gotway_options_from_input(user_input)}
            )
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="select_model",
            data_schema=vol.Schema(gotway_option_fields(dict(entry.options))),
            description_placeholders={"name": entry.title},
        )


class InMotionPasswordRepairFlow(_EntryRepairFlow):
    """Enter the InMotion V1 wheel password."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_password()

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_removed")
        errors: dict[str, str] = {}
        if user_input is not None:
            password, error = resolve_password(user_input, entry.data.get(CONF_INMOTION_PASSWORD))
            if error:
                errors[CONF_INMOTION_PASSWORD] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_INMOTION_PASSWORD: password}
                )
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(password_schema_fields(*password_defaults(dict(entry.data)))),
            errors=errors,
            description_placeholders={"name": entry.title},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for one of this integration's issues."""
    entry_id = str((data or {}).get("entry_id", ""))
    if issue_id.startswith(f"{ISSUE_GOTWAY_MODEL}_"):
        return GotwayModelRepairFlow(entry_id)
    if issue_id.startswith(f"{ISSUE_INMOTION_PASSWORD}_"):
        return InMotionPasswordRepairFlow(entry_id)
    raise ValueError(f"Unknown issue {issue_id}")
