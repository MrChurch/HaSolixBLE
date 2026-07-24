"""Solarbank 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import os
import time
from enum import Enum

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import GridStatus, LightMode, SBPowerCutoff, SBUsageMode, TemperatureUnit


CMD_SB2_SET_SCHEDULE = bytes.fromhex("405e")
CMD_SB2_SET_MAX_LOAD = bytes.fromhex("4080")
CMD_SB2_SET_RESERVED_POWER = bytes.fromhex("4067")
CMD_SB2_SET_LIGHT = bytes.fromhex("4068")


class MaxLoadSB2(Enum):
    """
    Maximum output power of the Solarbank 2 in watts.
    
    Only specific values are allowed.
    """

    #: The maximum load is unknown.
    UNKNOWN = -1

    #: 350 watts.
    W350 = 350

    #: 600 watts.
    W600 = 600

    #: 800 watts.
    W800 = 800

    #: 1000 watts.
    W1000 = 1000


class Solarbank2(SolixBLEDevice):
    """
    SolarBank 2 Power Station.

    Use this class to connect and monitor a Solarbank 2 power station.
    This model is also known as the A17C1.

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a legacy Solarbank 2 command with a current Unix timestamp."""
        if not self.negotiated:
            raise ConnectionError("Not connected to device")
        timestamp = int(time.time()).to_bytes(4, "little")
        encrypted = self._encrypt_payload(payload + bytes.fromhex("fe0503") + timestamp)
        packet = self._build_packet(bytes.fromhex("03000f"), cmd, encrypted)
        await self._client.write_gatt_char(self._command_characteristic, packet)

    @staticmethod
    def _build_set_schedule_payload(power_w: int) -> bytes:
        """Build the observed uniform seven-day 405e schedule payload."""
        if not 0 <= power_w <= 800:
            raise ValueError("power_w must be between 0 and 800 W")
        schedule = (0).to_bytes(2, "little") + (1440).to_bytes(2, "little")
        schedule += power_w.to_bytes(2, "little") + bytes.fromhex("5000")
        payload = bytearray.fromhex("a10121a2020101")
        for day in range(7):
            base = 0xA3 + 4 * day
            payload += bytes([base]) + bytes.fromhex("020101")
            payload += bytes([base + 1]) + bytes.fromhex("0904") + schedule
            payload += bytes([base + 2]) + bytes.fromhex("020100")
            payload += bytes([base + 3]) + bytes.fromhex("0104")
        payload += bytes.fromhex("fd0503") + os.urandom(4)
        return bytes(payload)

    async def set_schedule(self, power_w: int) -> None:
        """Set a uniform all-day Solarbank 2 schedule."""
        await self._send_command(CMD_SB2_SET_SCHEDULE, self._build_set_schedule_payload(power_w))

    @staticmethod
    def _build_set_max_load_payload(load: MaxLoadSB2) -> bytes:
        """Build the observed 4080 maximum-load payload."""
        if load is MaxLoadSB2.UNKNOWN:
            raise ValueError("MaxLoadSB2.UNKNOWN is not a valid setter input")
        watts = load.value.to_bytes(2, "little")
        return bytes.fromhex("a10121a20302") + watts + bytes.fromhex("a303020000")

    async def set_max_load(self, load: MaxLoadSB2) -> None:
        """Set the Solarbank 2 AC output limit."""
        await self._send_command(CMD_SB2_SET_MAX_LOAD, self._build_set_max_load_payload(load))

    @staticmethod
    def _build_set_light_payload(light_on: bool) -> bytes:
        """Build the observed 4068 light-switch payload."""
        state = 0 if light_on else 1
        return bytes.fromhex(f"a10121a2020100a30201{state:02x}")

    async def set_light_switch(self, light_on: bool) -> None:
        """Set the Solarbank 2 status light."""
        await self._send_command(CMD_SB2_SET_LIGHT, self._build_set_light_payload(light_on))

    @staticmethod
    def _build_set_reserved_power_payload(level: SBPowerCutoff) -> bytes:
        """Build the captured 4067 reserved-power payload."""
        mapping = {5: 4, 10: 5}
        if level is SBPowerCutoff.UNKNOWN or level.value not in mapping:
            raise ValueError("Only captured 5% and 10% reserved-power values are supported")
        pct = level.value
        return bytes.fromhex(
            f"a10121a20201{pct:02x}a30201{mapping[pct]:02x}a40201{pct:02x}"
        )

    async def set_reserved_power(self, level: SBPowerCutoff) -> None:
        """Set the captured Solarbank 2 reserved-power level."""
        await self._send_command(
            CMD_SB2_SET_RESERVED_POWER, self._build_set_reserved_power_payload(level)
        )

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=1)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a6", begin=1))])

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a7", begin=1))])

    @property
    def software_version_expansion(self) -> str:
        """Software version of any expansion batteries.

        If there is no expansion battery then it will be "0".

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a8", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("aa", begin=1, signed=True)

    @property
    def solar_power_in(self) -> float:
        """Total Solar Power In.

        :returns: Total solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ab", begin=1) / 10.0

    @property
    def ac_power_out(self) -> float:
        """AC Power Out.

        :returns: Total AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=1) / 10.0

    @property
    def battery_percentage_aggregate(self) -> int:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def battery_charge_power(self) -> float:
        """Battery charging power.

        :returns: Total battery power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b0", begin=1) / 100.0

    @property
    def pv_yield(self) -> float:
        """Solar energy generated in kWh.

        :returns: Total solar energy generated or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b1", begin=1) / 10000.0

    @property
    def charged_energy(self) -> float:
        """Total accumulated energy that passed through the battery in kWh

        :returns: The amount of energy or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        # The / 100 000 is correct despite all other divisors being 10 000.
        # This is the "Storage" stats field in the Anker app
        return self._parse_int("b2", begin=1) / 100000.0

    @property
    def output_energy(self) -> float:
        """Output energy in kWh.

        :returns: Total energy output or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b3", begin=1) / 10000.0

    @property
    def battery_discharge_power(self) -> float:
        """Battery discharging power.

        :returns: Total battery power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b7", begin=1) / 100.0

    @property
    def grid_to_home_power(self) -> float:
        """Grid to home power.

        :returns: Power from grid to home or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bc", begin=1) / 10.0

    @property
    def pv_to_grid_power(self) -> float:
        """PV to grid power.

        :returns: Power from PV to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bd", begin=1) / 10.0

    @property
    def grid_import_energy(self) -> float:
        """Grid import energy.

        :returns: Total energy imported from grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("be", begin=1) / 10000.0

    @property
    def grid_export_energy(self) -> float:
        """Grid export energy.

        :returns: Total energy exported to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bf", begin=1) / 10000.0

    @property
    def house_demand(self) -> float:
        """House demand power.

        :returns: Power used by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c4", begin=1) / 10.0

    @property
    def ac_power_out_sockets(self) -> float:
        """AC Power Out to sockets.

        :returns: AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c8", begin=1) / 10.0

    @property
    def consumed_energy(self) -> float:
        """Consumed energy by house.

        :returns: Total energy consumed by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c9", begin=1) / 10000.0

    @property
    def solar_pv_1_power_in(self) -> float:
        """Solar Power In for port 1.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ca", begin=1) / 10.0

    @property
    def solar_pv_2_power_in(self) -> float:
        """Solar Power In for port 2.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cb", begin=1) / 10.0

    @property
    def solar_pv_3_power_in(self) -> float:
        """Solar Power In for port 3.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cc", begin=1) / 10.0

    @property
    def solar_pv_4_power_in(self) -> float:
        """Solar Power In for port 4.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cd", begin=1) / 10.0

    @property
    def power_out(self) -> float:
        """Total Power Out.

        :returns: Total power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("d3", begin=1) / 10.0

    @property
    def error_code(self) -> int:
        """Device error code.

        :returns: Error code or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Temperature unit setting.

        :returns: Temperature unit (Celsius or Fahrenheit).
        """
        return TemperatureUnit(self._parse_int("a9", begin=1))

    @property
    def output_cutoff_data(self) -> SBPowerCutoff:
        """
        Output cutoff threshold in %.

        Minimum battery SOC to maintain.

        :returns: Output cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b4", begin=1))

    @property
    def lowpower_input_data(self) -> int:
        """Low power input data.

        :returns: Low power input data or default int value.
        """
        return self._parse_int("b5", begin=1)

    @property
    def input_cutoff_data(self) -> SBPowerCutoff:
        """Input cutoff threshold in %.

        :returns: Input cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b6", begin=1))

    @property
    def max_load(self) -> MaxLoadSB2:
        """
        Maximum output power in watts.
        
        Maximum legal value depends on country of operation.

        :returns: Maximum load as a MaxLoadSB2 enum value.
        """
        return MaxLoadSB2(self._parse_int("c2", begin=1))

    @property
    def usage_mode(self) -> SBUsageMode:
        """Usage mode.

        :returns: Usage mode as a SBUsageMode enum value.
        """
        return SBUsageMode(self._parse_int("c6", begin=1))

    @property
    def home_load_preset(self) -> int:
        """Home load preset in watts.

        :returns: Home load preset in watts or default int value.
        """
        return self._parse_int("c7", begin=1)

    @property
    def light_mode(self) -> LightMode:
        """Light mode. Normal or Mood.

        :returns: Light mode.
        """
        return LightMode(self._parse_int("d2", begin=1))

    @property
    def grid_status(self) -> GridStatus:
        """Grid connection status.

        :returns: Grid status.
        """
        return GridStatus(self._parse_int("e0", begin=1))

    @property
    def light_on(self) -> bool | None:
        """Whether the light is switched on.
        Original value is inverted because it is called "light_off_switch"

        :returns: True if light is on, False if off.
        """
        return (
            not bool(self._parse_int("e1", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def battery_heating(self) -> bool | None:
        """Whether the battery is currently heating.

        :returns: True if heating, False if not heating.
        """
        return (
            bool(self._parse_int("e8", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )


class Solarbank2AC(Solarbank2):
    """Solarbank 2 AC model using the Solarbank 2 telemetry schema.

    The AC variant currently exposes the same authenticated BLE telemetry
    fields and controls as the existing Solarbank 2 implementation.  It is a
    separate class so Home Assistant can distinguish the device explicitly
    while we collect AC-variant captures for any future field differences.
    """

    @property
    def output_cutoff_data(self) -> SBPowerCutoff:
        """Return the AC output cutoff when the payload exposes it."""
        try:
            return super().output_cutoff_data
        except ValueError:
            return SBPowerCutoff.UNKNOWN

    @property
    def input_cutoff_data(self) -> SBPowerCutoff:
        """Return the AC input cutoff when the payload exposes it."""
        try:
            return super().input_cutoff_data
        except ValueError:
            return SBPowerCutoff.UNKNOWN

    @property
    def max_load(self) -> MaxLoadSB2:
        """Return the AC maximum load or UNKNOWN for an unsupported value."""
        try:
            return super().max_load
        except ValueError:
            return MaxLoadSB2.UNKNOWN

    @property
    def usage_mode(self) -> SBUsageMode:
        """Return the AC usage mode or UNKNOWN for an unsupported value."""
        try:
            return super().usage_mode
        except ValueError:
            return SBUsageMode.UNKNOWN

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Return Unknown when the AC telemetry uses a non-enum field."""
        try:
            return super().temperature_unit
        except ValueError:
            return TemperatureUnit.UNKNOWN

