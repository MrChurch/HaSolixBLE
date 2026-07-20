"""Solarbank 3 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import re

from bleak.backends.device import BLEDevice

from ..const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_STRING
from ..device import SolixBLEDevice
from ..sb3_protocol import (
    SB3_MAX_LOAD_VALUES,
    SB3_SET_MAX_LOAD_COMMAND,
    SB3_SET_SCHEDULE_COMMAND,
    build_sb3_max_load_plaintext,
    build_sb3_schedule_plaintext,
)


class Solarbank3(SolixBLEDevice):
    """
    SolarBank 3 Power Station.

    Use this class to connect and monitor a Solarbank 3 power station.
    This model is also known as the A17C5.

    .. note::
        This model was added using data from anker-solix-api. It has not been
        tested!

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """
    _UUID_COMMAND: str = "8c850002-0302-41c5-b46e-cf057c562025"
    _UUID_TELEMETRY: str = "8c850003-0302-41c5-b46e-cf057c562025"
    _EXPECTED_TELEMETRY_LENGTH: int = 253

    def __init__(self, ble_device: BLEDevice) -> None:
        """Initialize the Solarbank 3 and its staged schedule target."""
        super().__init__(ble_device)
        self._schedule_power_target = 0
        self._max_load_target = 1200

    @property
    def schedule_power_target(self) -> int:
        """Return the staged output target used by the apply button."""
        return self._schedule_power_target

    def set_schedule_power_target(self, power_w: int) -> None:
        """Stage a schedule target without writing the device."""
        if not isinstance(power_w, int) or isinstance(power_w, bool):
            raise TypeError("power_w must be an integer")
        if not 0 <= power_w <= 1200 or power_w % 50:
            raise ValueError("power_w must be between 0 and 1200 W in 50 W steps")
        self._schedule_power_target = power_w

    @property
    def max_load_target(self) -> int:
        """Return the staged maximum-load limit."""
        return self._max_load_target

    def set_max_load_target(self, max_load_w: int) -> None:
        """Stage a supported maximum-load limit without writing the device."""
        if max_load_w not in SB3_MAX_LOAD_VALUES:
            raise ValueError(
                "max_load_w must be one of: "
                + ", ".join(str(value) for value in SB3_MAX_LOAD_VALUES)
                + " W"
            )
        self._max_load_target = max_load_w

    async def set_schedule(
        self,
        power_w: int,
        *,
        start_minutes: int = 0,
        end_minutes: int = 1440,
    ) -> None:
        """Set a uniform seven-day output schedule on the Solarbank 3.

        This is the local BLE equivalent of the app's ``405e`` write.  The
        command is sent only after the authenticated SB3 session is ready;
        :meth:`SolixBLEDevice._send_command` adds the current replay timestamp
        and applies the negotiated AES-GCM session encryption.
        """
        payload = build_sb3_schedule_plaintext(
            power_w,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
        )
        await self._send_sb3_command(SB3_SET_SCHEDULE_COMMAND, payload)

    async def set_max_load(self, max_load_w: int) -> None:
        """Set the Solarbank 3 maximum output/load limit via ``4080``."""
        payload = build_sb3_max_load_plaintext(max_load_w)
        await self._send_sb3_command(SB3_SET_MAX_LOAD_COMMAND, payload)

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=1)

    @property
    def battery_percentage_aggregate(self) -> float:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        # Solarbank 3 uses ``a3`` for the battery state of charge.  The
        # similarly shaped ``a5`` field is the unit temperature, not an
        # aggregate battery percentage.
        return float(self._parse_int("a3", begin=1))

    @property
    def battery_health(self) -> float:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return float(self._parse_int("a6", begin=1))

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Total Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_float("ab")

    @property
    def pv_yield(self) -> float:
        """Solar power generated.

        :returns: Total solar power generated or default int value.
        """
        # Firmware occasionally reports a signed negative counter after a
        # schedule reset. Energy cannot be negative, so expose a safe value.
        return max(0.0, self._parse_float("ac"))

    @property
    def house_demand(self) -> int:
        """House demand power.

        :returns: Power used by house or default int value.
        """
        return self._parse_float("b1")

    @property
    def house_consumption(self) -> int:
        """House consumption power.

        Don't ask me how this differs from house demand, I have no idea.

        :returns: Power used by house or default int value.
        """
        return self._parse_float("b2")

    @property
    def battery_power(self) -> int:
        """Battery power in and out.

        I don't know what direction is which.

        :returns: Power in/out of battery or default int value.
        """
        return self._parse_int("b6", begin=1, signed=True)

    @property
    def schedule_power(self) -> int:
        """Current scheduled output power reported by telemetry (``b9``)."""
        return self._parse_int("b9", begin=1)

    @property
    def charged_energy(self) -> int:
        """Energy into battery?

        :returns: Energy into battery or default int value.
        """
        return self._parse_int("b7", begin=1)

    @property
    def discharged_energy(self) -> int:
        """Energy out of battery?

        :returns: Energy out of battery or default int value.
        """
        return self._parse_int("b8", begin=1)

    @property
    def grid_power(self) -> int:
        """Grid power in and out.

        I don't know what direction is which.

        :returns: Power in/out of grid or default int value.
        """
        return int(self._parse_float("bd"))

    @property
    def grid_import_energy(self) -> int:
        """Grid import energy.

        :returns: Total energy imported from grid or default int value.
        """
        return self._parse_int("be", begin=1)

    @property
    def grid_export_energy(self) -> int:
        """Grid export energy.

        :returns: Total energy exported to grid or default int value.
        """
        return int(self._parse_float("bf"))

    @property
    def solar_pv_1_power_in(self) -> int:
        """Solar Power In for port 1.

        :returns: Solar power in or default int value.
        """
        return self._parse_float("c7")

    @property
    def solar_pv_2_power_in(self) -> int:
        """Solar Power In for port 2.

        :returns: Solar power in or default int value.
        """
        return self._parse_float("c8")

    @property
    def solar_pv_3_power_in(self) -> int:
        """Solar Power In for port 3.

        :returns: Solar power in or default int value.
        """
        return self._parse_float("c9")

    @property
    def solar_pv_4_power_in(self) -> int:
        """Solar Power In for port 4.

        :returns: Solar power in or default int value.
        """
        return self._parse_float("ca")

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        # ``a5`` is reported as a two-byte integer in degrees Celsius.  The
        # ``cc`` field is a separate status value and is not the temperature.
        return self._parse_int("a5", begin=1, signed=True)

    def _expansion_battery(self, slot: int) -> tuple[str | None, int | None, int | None]:
        """Decode one expansion-battery record from the decrypted 4409 blob.

        The record marker is ``63 01 <slot> <temperature> <soc> <health>``;
        the 16 ASCII bytes immediately before it are the battery serial.
        BP1600 uses ``00`` as the byte before the SOC while BP2700 uses
        ``02``; that byte is a format marker, not part of the value.
        """
        payload = self.sb3_battery_metadata
        if payload is None:
            return None, None, None

        marker = bytes((0x63, 0x01, slot))
        start = 0
        while (index := payload.find(marker, start)) >= 16:
            if index + 7 > len(payload):
                start = index + 1
                continue
            serial_bytes = payload[index - 16:index]
            try:
                serial = serial_bytes.decode("ascii")
            except UnicodeDecodeError:
                start = index + 1
                continue
            # Some expansion records repeat the complete serial after the
            # compact 16-byte display field. Prefer that longer ASCII run.
            trailing_runs = re.findall(rb"[A-Z0-9]{16,}", payload[index + 7 :])
            if slot == 3 and trailing_runs:
                serial = max((run.decode("ascii") for run in trailing_runs), key=len)
            temperature = payload[index + 3]
            percentage = payload[index + 5]
            return serial, percentage, temperature
        return None, None, None

    def _expansion_battery_value(self, slot: int, value: int) -> int | str | None:
        """Return one decoded expansion-battery value."""
        serial, percentage, temperature = self._expansion_battery(slot)
        return (serial, percentage, temperature)[value]

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries reported by the SB3 metadata."""
        return sum(self._expansion_battery(slot)[0] is not None for slot in range(1, 6))

    @property
    def expansion_battery_1_serial_number(self) -> str | None:
        return self._expansion_battery_value(2, 0)

    @property
    def expansion_battery_1_percentage(self) -> int | None:
        return self._expansion_battery_value(2, 1)

    @property
    def expansion_battery_1_temperature(self) -> int | None:
        return self._expansion_battery_value(2, 2)

    @property
    def expansion_battery_2_serial_number(self) -> str | None:
        return self._expansion_battery_value(3, 0)

    @property
    def expansion_battery_2_percentage(self) -> int | None:
        return self._expansion_battery_value(3, 1)

    @property
    def expansion_battery_2_temperature(self) -> int | None:
        return self._expansion_battery_value(3, 2)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        # SB3 reports the live inverter output as a typed float in ``ad``.
        # ``d3`` is present in the packet but remains a status/reserved field
        # (zero in captures even while the unit is delivering 150--750 W).
        return round(self._parse_float("ad"))

    @property
    def grid_to_home_power(self) -> int:
        """PV maximum limit reported by telemetry field ``d5``.

        The field was initially labelled ``Grid to Home`` from the generic
        Solarbank mapping.  SB3 captures show it is the PV maximum value.
        """
        return self._parse_int("d5", begin=1)
