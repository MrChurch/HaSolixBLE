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

    def __init__(self, ble_device) -> None:
        """Initialize Solarbank 2 state and staged control values."""
        super().__init__(ble_device)
        self._schedule_power_target = 0
        self._max_load_target = MaxLoadSB2.W800.value

    @property
    def schedule_power_target(self) -> int:
        """Return the staged all-day schedule target in watts."""
        return self._schedule_power_target

    def set_schedule_power_target(self, power_w: int) -> None:
        """Stage an all-day schedule target without writing the device."""
        if not 0 <= power_w <= 800 or power_w % 10:
            raise ValueError("power_w must be between 0 and 800 W in 10 W steps")
        self._schedule_power_target = power_w

    @property
    def max_load_target(self) -> int:
        """Return the staged maximum-load target in watts."""
        return self._max_load_target

    def set_max_load_target(self, load_w: int) -> None:
        """Stage a maximum-load target without writing the device."""
        if load_w not in {member.value for member in MaxLoadSB2 if member is not MaxLoadSB2.UNKNOWN}:
            raise ValueError(f"unsupported Solarbank 2 maximum load: {load_w}")
        self._max_load_target = load_w

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
        """Build the observed uniform seven-day ``405e`` schedule payload.

        Anker's Solarbank 2 app writes schedule targets in 10 W increments.
        The Home Assistant number entity already uses that resolution, but this
        builder is also callable directly.  Keep the same bound here so an
        automation or future caller cannot bypass the validated wire format.
        """
        if not isinstance(power_w, int) or isinstance(power_w, bool):
            raise TypeError("power_w must be an integer")
        if not 0 <= power_w <= 800 or power_w % 10:
            raise ValueError("power_w must be between 0 and 800 W in 10 W steps")
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
    """Solarbank 2 AC model with its own authenticated telemetry schema.

    The AC variant shares control commands with Solarbank 2, but its ``c405``
    telemetry uses a different field layout.  In particular, applying the
    original Solarbank 2 integer divisors to its typed values creates
    impossible power and energy values.  The Home Assistant sensor platform
    therefore exposes only independently verified fields until the remaining
    layout has been captured and mapped.
    """

    _DISPLAY_NAME = "Solarbank 2 E1600 AC"

    # A17C0/Solarbank 2 AC uses typed float32 values (``05`` + LE float32)
    # in c405.  This is intentionally kept in this subclass: the legacy
    # Solarbank 2 integer/divisor mapping and the A17C5/Solarbank 3 mapping
    # are different protocols and must not influence each other.  The actual
    # meanings of these tags remain unverified and must not be exposed as
    # named Home Assistant power sensors yet.
    _A17C0_CANDIDATE_FLOAT_FIELDS = (
        "b0",
        "b1",
        "b2",
        "b3",
        "b4",
        "c4",
    )

    def __init__(self, ble_device) -> None:
        """Initialize AC telemetry state without staging a schedule override."""
        super().__init__(ble_device)
        self._schedule_power_target_staged = False

    @property
    def schedule_power_target(self) -> int:
        """Return the staged target or the live A17C0 custom-plan value."""
        if (
            not self._schedule_power_target_staged
            and self._data is not None
            and "c5" in self._data
        ):
            return self.schedule_power
        return self._schedule_power_target

    def set_schedule_power_target(self, power_w: int, *, staged: bool = True) -> None:
        """Stage an AC schedule target without changing the device yet."""
        super().set_schedule_power_target(power_w)
        self._schedule_power_target_staged = staged

    def sync_schedule_power_target(self) -> int | None:
        """Use live ``c5`` telemetry as the initial custom-plan slider value."""
        if (
            self._schedule_power_target_staged
            or self._data is None
            or "c5" not in self._data
        ):
            return None
        self._schedule_power_target_staged = False
        self._schedule_power_target = self.schedule_power
        return self._schedule_power_target

    @property
    def schedule_power(self) -> int:
        """Return the active A17C0 custom-plan output from ``c5``."""
        return round(self._parse_float("c5"))

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Route AC controls through its separately negotiated AES-GCM session."""
        await self._send_sb2ac_command(cmd, payload)

    async def set_schedule(self, power_w: int) -> None:
        """Write the uniform plan and resume following its reported value."""
        await super().set_schedule(power_w)
        self._schedule_power_target = power_w
        self._schedule_power_target_staged = False

    @property
    def sb2ac_telemetry_candidates(self) -> dict[str, float]:
        """Return unlabelled A17C0 float fields for controlled correlation.

        These values are exposed to the debug logger with their wire tags so
        controlled schedule tests can map them without publishing guessed
        Home Assistant sensors.  Static APK labels alone are not sufficient:
        the E1600 AC capture has no PV modules while ``b1`` is non-zero.
        """
        if self._data is None:
            return {}
        return {
            key: self._parse_float(key)
            for key in self._A17C0_CANDIDATE_FLOAT_FIELDS
            if key in self._data
        }

    @property
    def power_out(self) -> int:
        """Current AC output from the verified A17C0 ``ad`` float.

        With a 150 W custom schedule applied, three subsequent local c405
        frames reported ``ad = 151 W``.  Keep this model-specific mapping out
        of the legacy Solarbank 2 and Solarbank 3 decoders.
        """
        return round(self._parse_float("ad"))

    @property
    def grid_import_power(self) -> int:
        """Current grid import power from the verified A17C0 ``d7`` float.

        In the 150 W schedule capture, ``ad = 151 W`` plus ``d7 = 225 W``
        equals the signed ``c4 = -376 W`` balance.  This identifies d7 as the
        grid contribution to the house, not grid export.
        """
        return round(self._parse_float("d7"))

    @property
    def temperature(self) -> int:
        """Return the A17C0 unit temperature from the typed ``a5`` integer.

        Consecutive owned E1600 AC captures report ``a5`` as 35, 36, and
        37 while the other device-status fields stay stable.  That is the
        expected behaviour of the unit temperature; interpreting it as the
        legacy SB2 error-code field produced misleading persistent errors.
        """
        return self._parse_int("a5", begin=1, signed=True)

    @property
    def discharge_limit(self) -> int:
        """Return the configured lower state-of-charge limit from ``b5``.

        The value follows the tested A17C0 custom-plan discharge limit (10 %
        in the current capture).  It is a configuration value, not live power.
        """
        return self._parse_int("b5", begin=1)

    @property
    def charge_limit(self) -> int:
        """Return the configured upper state-of-charge limit from ``b7``.

        The value follows the tested A17C0 charge limit (95 % in the current
        capture).  It is intentionally separate from the live battery SOC.
        """
        return self._parse_int("b7", begin=1)

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

