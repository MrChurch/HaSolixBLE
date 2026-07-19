"""Solarbank 3 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

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
        if not 0 <= power_w <= 800:
            raise ValueError("power_w must be between 0 and 800 W")
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

        return float(self._parse_int("a5", begin=1))

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
    def pv_yield(self) -> int:
        """Solar power generated.

        :returns: Total solar power generated or default int value.
        """
        return self._parse_float("ac")

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
        return self._parse_int("cc", begin=1, signed=True)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("d3", begin=1)

    @property
    def grid_to_home_power(self) -> int:
        """Grid to home power.

        :returns: Power from grid to home or default int value.
        """
        return self._parse_int("d5", begin=1)
