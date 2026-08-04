"""Select entities for Solix BLE devices."""

from __future__ import annotations

import time

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .SolixBLE import Solarbank2AC, Solarbank3
from .SolixBLE.devices.solarbank2 import MaxLoadSB2
from .SolixBLE.device import SolixBLEDevice
from .SolixBLE.sb3_protocol import (
    SB3_MAX_LOAD_VALUES,
    SB3_SCHEDULE_MODE_CHARGE,
    SB3_SCHEDULE_MODE_DISCHARGE,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[SolixBLEDevice],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solarbank 3 select entities."""
    device = config_entry.runtime_data
    if isinstance(device, Solarbank3):
        async_add_entities(
            [Solarbank3MaxLoadSelect(device), Solarbank3ScheduleModeSelect(device)]
        )
    elif isinstance(device, Solarbank2AC):
        async_add_entities(
            [Solarbank2ACMaxLoadSelect(device), Solarbank2ACUsageModeSelect(device)]
        )


class Solarbank2ACMaxLoadSelect(RestoreEntity, SelectEntity):
    """Staged maximum-load selector for Solarbank 2 AC."""

    _attr_has_entity_name = True
    _attr_name = "Maximum load limit"
    _attr_icon = "mdi:flash-outline"

    def __init__(self, device: Solarbank2AC) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_max_load_limit"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_options = [str(member.value) for member in MaxLoadSB2 if member is not MaxLoadSB2.UNKNOWN]
        self._attr_current_option = str(device.max_load_target)

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._device.add_callback(self._state_change_callback)
        live_target = self._device.sync_max_load_target()
        if live_target is not None:
            self._attr_current_option = str(live_target)
            return
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            # A restored HA state is only a fallback until bd telemetry arrives.
            self._device.set_max_load_target(int(last_state.state), staged=False)
            self._attr_current_option = last_state.state

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the live maximum-load callback."""
        self._device.remove_callback(self._state_change_callback)

    def _state_change_callback(self) -> None:
        """Refresh the selector from the live limit without losing staging."""
        live_target = self._device.sync_max_load_target()
        if live_target is None:
            return
        self._attr_current_option = str(live_target)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise ValueError(f"unsupported Solarbank 2 maximum load: {option}")
        self._device.set_max_load_target(int(option))
        self._attr_current_option = option
        self.async_write_ha_state()


class Solarbank2ACUsageModeSelect(RestoreEntity, SelectEntity):
    """Direct Custom/Self consumption control for Solarbank 2 AC."""

    _attr_has_entity_name = True
    _attr_name = "Usage mode"
    _attr_icon = "mdi:home-lightning-bolt-outline"
    _PENDING_CONFIRMATION_SECONDS = 10.0

    def __init__(self, device: Solarbank2AC) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_usage_mode_control"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_options = ["Custom", "Self consumption"]
        self._attr_current_option = (
            device.usage_mode if device.usage_mode in self._attr_options else None
        )
        self._pending_option: str | None = None
        self._pending_until = 0.0

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._device.add_callback(self._state_change_callback)
        self._sync_from_telemetry()

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the live mode callback."""
        self._device.remove_callback(self._state_change_callback)

    def _sync_from_telemetry(self) -> None:
        """Adopt confirmed live state without reverting a fresh selection."""
        live_mode = self._device.usage_mode
        if live_mode not in self._attr_options:
            return
        if self._pending_option is not None:
            if live_mode == self._pending_option:
                self._pending_option = None
            elif time.monotonic() < self._pending_until:
                return
            else:
                self._pending_option = None
        self._attr_current_option = live_mode

    def _state_change_callback(self) -> None:
        """Refresh from c405 after a device-confirmed mode transition."""
        before = self._attr_current_option
        self._sync_from_telemetry()
        if self._attr_current_option != before:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise ValueError(f"unsupported Solarbank 2 AC usage mode: {option}")
        await self._device.set_usage_mode(option == "Custom")
        self._pending_option = option
        self._pending_until = time.monotonic() + self._PENDING_CONFIRMATION_SECONDS
        self._attr_current_option = option
        self.async_write_ha_state()


class Solarbank3ScheduleModeSelect(RestoreEntity, SelectEntity):
    """Staged direction for the Solarbank 3 schedule."""

    _attr_has_entity_name = True
    _attr_name = "Schedule mode"
    _attr_icon = "mdi:swap-vertical"
    def __init__(self, device: Solarbank3) -> None:
        """Initialize the staged schedule mode selector."""
        self._device = device
        self._attr_unique_id = f"{device.address}_schedule_mode"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_options = [
            SB3_SCHEDULE_MODE_DISCHARGE,
            SB3_SCHEDULE_MODE_CHARGE,
        ]
        self._attr_current_option = device.schedule_mode

    @property
    def available(self) -> bool:
        """Return whether the underlying BLE device is available."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Restore the staged schedule mode after a restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state not in self._attr_options:
            return
        self._device.set_schedule_mode(last_state.state)
        self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Stage charging or discharging; the apply button performs the write."""
        if option not in self._attr_options:
            raise ValueError(f"unsupported Solarbank 3 schedule mode: {option}")
        self._device.set_schedule_mode(option)
        self._attr_current_option = option
        self.async_write_ha_state()


class Solarbank3MaxLoadSelect(RestoreEntity, SelectEntity):
    """Staged maximum output/load limit for the Solarbank 3."""

    _attr_has_entity_name = True
    _attr_name = "Maximum load limit"
    _attr_icon = "mdi:flash-outline"

    def __init__(self, device: Solarbank3) -> None:
        """Initialize the staged maximum-load selector."""
        self._device = device
        self._attr_unique_id = f"{device.address}_max_load_limit"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_options = [str(value) for value in SB3_MAX_LOAD_VALUES]
        self._attr_current_option = str(device.max_load_target)

    @property
    def available(self) -> bool:
        """Return whether the underlying BLE device is available."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Restore the staged maximum-load limit after a restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state not in self._attr_options:
            return
        value = int(last_state.state)
        self._device.set_max_load_target(value)
        self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Stage a new maximum-load limit; the apply button performs the write."""
        if option not in self._attr_options:
            raise ValueError(f"unsupported Solarbank 3 maximum load: {option}")
        self._device.set_max_load_target(int(option))
        self._attr_current_option = option
        self.async_write_ha_state()
