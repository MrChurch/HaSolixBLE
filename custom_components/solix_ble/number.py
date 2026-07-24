"""Number entities for Solix BLE devices."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .SolixBLE import Solarbank2AC, Solarbank3
from .SolixBLE.device import SolixBLEDevice


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[SolixBLEDevice],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solarbank 3 number entities."""
    device = config_entry.runtime_data
    if isinstance(device, Solarbank3):
        async_add_entities([Solarbank3ScheduleNumber(device)])
    elif isinstance(device, Solarbank2AC):
        async_add_entities([Solarbank2ACScheduleNumber(device)])


class Solarbank2ACScheduleNumber(RestoreEntity, NumberEntity):
    """Staged all-day schedule target for Solarbank 2 AC."""

    _attr_has_entity_name = True
    _attr_name = "Schedule power target"
    _attr_icon = "mdi:solar-power"
    _attr_native_min_value = 0
    _attr_native_max_value = 800
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "W"
    _attr_mode = "slider"

    def __init__(self, device: Solarbank2AC) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_schedule_power_target"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_native_value = device.schedule_power_target

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = int(float(last_state.state))
        except ValueError:
            return
        if 0 <= value <= 800 and value % 10 == 0:
            self._device.set_schedule_power_target(value)
            self._attr_native_value = value

    async def async_set_native_value(self, value: float) -> None:
        target = int(round(value / 10) * 10)
        self._device.set_schedule_power_target(target)
        self._attr_native_value = target
        self.async_write_ha_state()


class Solarbank3ScheduleNumber(RestoreEntity, NumberEntity):
    """Staged all-day output target for the Solarbank 3 schedule."""

    _attr_has_entity_name = True
    _attr_name = "Schedule power target"
    _attr_icon = "mdi:solar-power"
    _attr_native_min_value = 0
    _attr_native_max_value = 1200
    _attr_native_step = 50
    _attr_native_unit_of_measurement = "W"
    _attr_mode = "slider"

    def __init__(self, device: Solarbank3) -> None:
        """Initialize the staged target."""
        self._device = device
        self._attr_unique_id = f"{device.address}_schedule_power_target"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )
        self._attr_native_value = device.schedule_power_target

    @property
    def available(self) -> bool:
        """Return whether the underlying BLE device is available."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Restore the staged target after Home Assistant restarts."""
        await super().async_added_to_hass()
        live_target = self._device.sync_schedule_power_target()
        if live_target is not None:
            self._attr_native_value = live_target
            return
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                value = int(float(last_state.state))
            except ValueError:
                value = self._device.schedule_power_target
            if 0 <= value <= 1200:
                value = int(round(value / 50) * 50)
                self._device.set_schedule_power_target(value)
                self._attr_native_value = value

    async def async_set_native_value(self, value: float) -> None:
        """Stage a new output target; the apply button performs the write."""
        target = int(round(value / 50) * 50)
        self._device.set_schedule_power_target(target)
        self._attr_native_value = target
        self.async_write_ha_state()
