"""Valve platform for the Moen/Flo shutoff valve device."""
from __future__ import annotations

import logging

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_SHUTOFF, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the shutoff valve entity, if this account has one."""
    from . import DATA_FLO_CLASSIC  # local import to avoid circular import at module load

    coordinator = hass.data.get(DATA_FLO_CLASSIC, {}).get(entry.entry_id)
    if coordinator is None:
        return

    entities = [
        FloShutoffValve(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if device.get("deviceType") == DEVICE_TYPE_SHUTOFF
    ]
    async_add_entities(entities)


class FloShutoffValve(CoordinatorEntity, ValveEntity):
    """Representation of a Flo smart water shutoff valve."""

    _attr_device_class = ValveDeviceClass.WATER
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    _attr_reports_position = False

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        device = coordinator.data.get(device_id, {})
        nickname = device.get("nickname", "Flo Shutoff Valve")
        self._attr_name = nickname
        self._attr_unique_id = f"{device_id}_valve"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=nickname,
            manufacturer="Moen",
            model=device.get("deviceModel", "Flo Shutoff"),
            sw_version=device.get("fwVersion"),
        )

    @property
    def _device(self) -> dict:
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        """Return True if the valve is closed."""
        last_known = self._device.get("valve", {}).get("lastKnown")
        if last_known is None:
            return None
        return last_known == "closed"

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict:
        device = self._device
        telemetry = device.get("telemetry", {}).get("current", {})
        return {
            "flow_rate_gpm": telemetry.get("gpm"),
            "pressure_psi": telemetry.get("psi"),
            "water_temperature_f": telemetry.get("tempF"),
            "target_state": device.get("valve", {}).get("target"),
            "system_mode": device.get("systemMode", {}).get("lastKnown"),
            "wifi_rssi": device.get("connectivity", {}).get("rssi"),
        }

    async def async_open_valve(self) -> None:
        """Open the valve."""
        await self.coordinator.client.async_set_valve(self._device_id, "open")
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self.coordinator.client.async_set_valve(self._device_id, "closed")
        await self.coordinator.async_request_refresh()
