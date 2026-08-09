"""Button entities for Solix BLE devices."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .SolixBLE import Solarbank2AC, Solarbank3
from .SolixBLE.devices.solarbank2 import MaxLoadSB2
from .SolixBLE.device import SolixBLEDevice


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[SolixBLEDevice],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solarbank 3 button entities."""
    device = config_entry.runtime_data
    if isinstance(device, Solarbank3):
        async_add_entities(
            [
                Solarbank3ScheduleApplyButton(device),
                Solarbank3MaxLoadApplyButton(device),
                Solarbank3PVMaxApplyButton(device),
            ]
        )
    elif isinstance(device, Solarbank2AC):
        async_add_entities(
            [Solarbank2ACScheduleApplyButton(device), Solarbank2ACMaxLoadApplyButton(device)]
        )


class Solarbank2ACScheduleApplyButton(ButtonEntity):
    """Apply the staged schedule to Solarbank 2 AC."""

    _attr_has_entity_name = True
    _attr_name = "Apply schedule"
    _attr_icon = "mdi:content-save-check"

    def __init__(self, device: Solarbank2AC) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_schedule_apply"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )

    @property
    def available(self) -> bool:
        return self._device.negotiated

    async def async_press(self) -> None:
        await self._device.set_schedule(self._device.schedule_power_target)


class Solarbank2ACMaxLoadApplyButton(ButtonEntity):
    """Apply the staged maximum load to Solarbank 2 AC."""

    _attr_has_entity_name = True
    _attr_name = "Apply maximum load limit"
    _attr_icon = "mdi:flash-check"

    def __init__(self, device: Solarbank2AC) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_max_load_apply"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )

    @property
    def available(self) -> bool:
        return self._device.negotiated

    async def async_press(self) -> None:
        await self._device.set_max_load(MaxLoadSB2(self._device.max_load_target))


class Solarbank3ScheduleApplyButton(ButtonEntity):
    """Apply the staged all-day schedule target to the Solarbank 3."""

    _attr_has_entity_name = True
    _attr_name = "Apply schedule"
    _attr_icon = "mdi:content-save-check"

    def __init__(self, device: Solarbank3) -> None:
        """Initialize the apply button."""
        self._device = device
        self._attr_unique_id = f"{device.address}_schedule_apply"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )

    @property
    def available(self) -> bool:
        """Enable writes only after this session reported its active plan."""
        return (
            self._device.negotiated
            and self._device.sb3_schedule_telemetry_ready
        )

    async def async_press(self) -> None:
        """Write the staged target as a uniform seven-day schedule."""
        await self._device.set_schedule(
            self._device.schedule_power_target,
            mode=self._device.schedule_mode,
        )


class Solarbank3MaxLoadApplyButton(ButtonEntity):
    """Apply the staged maximum-load limit to the Solarbank 3."""

    _attr_has_entity_name = True
    _attr_name = "Apply maximum load limit"
    _attr_icon = "mdi:flash-check"

    def __init__(self, device: Solarbank3) -> None:
        """Initialize the maximum-load apply button."""
        self._device = device
        self._attr_unique_id = f"{device.address}_max_load_apply"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )

    @property
    def available(self) -> bool:
        """Return whether the authenticated BLE session can accept writes."""
        return self._device.negotiated

    async def async_press(self) -> None:
        """Write the staged maximum-load limit."""
        await self._device.set_max_load(self._device.max_load_target)


class Solarbank3PVMaxApplyButton(ButtonEntity):
    """Apply the staged Solarbank 3 MPPT maximum input."""

    _attr_has_entity_name = True
    _attr_name = "Apply PV maximum input"
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, device: Solarbank3) -> None:
        """Initialize the MPPT maximum-input apply button."""
        self._device = device
        self._attr_unique_id = f"{device.address}_pv_maximum_input_apply"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            connections={(CONNECTION_BLUETOOTH, device.address)},
        )

    @property
    def available(self) -> bool:
        """Enable writes only after the current session reported field d5."""
        return self._device.negotiated and self._device.sb3_pv_max_telemetry_ready

    async def async_press(self) -> None:
        """Write the captured standalone ``a7`` limit payload."""
        await self._device.set_pv_max(self._device.pv_max_target)
