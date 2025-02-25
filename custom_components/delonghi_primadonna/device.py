"""Delongi primadonna device description"""
import asyncio
from binascii import hexlify
import logging
import uuid

from bleak import BleakClient
from bleak.exc import BleakDBusError, BleakError

from homeassistant.backports.enum import StrEnum
from homeassistant.components import bluetooth
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (AMERICANO_OFF, AMERICANO_ON, BYTES_CUP_LIGHT_OFF,
                    BYTES_CUP_LIGHT_ON, BYTES_POWER, COFFE_OFF, COFFE_ON,
                    COFFEE_GROUNDS_CONTAINER_DETACHED,
                    COFFEE_GROUNDS_CONTAINER_FULL, CONTROLL_CHARACTERISTIC,
                    DEBUG, DEVICE_READY, DEVICE_TURNOFF, DOMAIN, DOPPIO_OFF,
                    DOPPIO_ON, ESPRESSO2_OFF, ESPRESSO2_ON, ESPRESSO_OFF,
                    ESPRESSO_ON, HOTWATER_OFF, HOTWATER_ON, LONG_OFF, LONG_ON,
                    NAME_CHARACTERISTIC, STEAM_OFF, STEAM_ON, WATER_SHORTAGE,
                    WATER_TANK_DETACHED, START_COFFEE)


_LOGGER = logging.getLogger(__name__)


class AvailableBeverage(StrEnum):

    STEAM = 'steam'
    LONG = 'long'
    COFFEE = 'coffee'
    DOPIO = 'dopio'
    HOTWATER = 'hot_water'
    ESPRESSO = 'espresso'
    AMERICANO = 'americano'
    ESPRESSO2 = 'espresso2'
    NONE = 'none'


class NotificationType(StrEnum):

    STATUS = 'status'
    PROCESS = 'process'


class BeverageCommand:

    def __init__(self, on, off):
        self.on = on
        self.off = off


class BeverageNotify:

    def __init__(self, kind, description):
        self.kind = str(kind)
        self.description = str(description)


BEVERAGE_COMMANDS = {
    AvailableBeverage.STEAM: BeverageCommand(STEAM_ON, STEAM_OFF),
    AvailableBeverage.LONG: BeverageCommand(LONG_ON, LONG_OFF),
    AvailableBeverage.COFFEE: BeverageCommand(COFFE_ON, COFFE_OFF),
    AvailableBeverage.DOPIO: BeverageCommand(DOPPIO_ON, DOPPIO_OFF),
    AvailableBeverage.HOTWATER: BeverageCommand(HOTWATER_ON, HOTWATER_OFF),
    AvailableBeverage.ESPRESSO: BeverageCommand(ESPRESSO_ON, ESPRESSO_OFF),
    AvailableBeverage.AMERICANO: BeverageCommand(AMERICANO_ON, AMERICANO_OFF),
    AvailableBeverage.ESPRESSO2: BeverageCommand(ESPRESSO2_ON, ESPRESSO2_OFF)
}

DEVICE_NOTIFICATION = {
    str(bytearray(DEVICE_READY)): BeverageNotify(
        NotificationType.STATUS, 'DeviceOK'),
    str(bytearray(DEVICE_TURNOFF)): BeverageNotify(
        NotificationType.STATUS, 'DeviceOFF'),
    str(bytearray(WATER_TANK_DETACHED)): BeverageNotify(
        NotificationType.STATUS, 'NoWaterTank'),
    str(bytearray(WATER_SHORTAGE)): BeverageNotify(
        NotificationType.STATUS, 'NoWater'),
    str(bytearray(COFFEE_GROUNDS_CONTAINER_DETACHED)): BeverageNotify(
        NotificationType.STATUS, 'NoGroundsContainer'),
    str(bytearray(COFFEE_GROUNDS_CONTAINER_FULL)): BeverageNotify(
        NotificationType.STATUS, 'GroundsContainerFull'),
    str(bytearray(START_COFFEE)): BeverageNotify(
        NotificationType.STATUS, 'START_COFFEE')
}


class DelonghiDeviceEntity:
    """Entity class for the Delonghi devices"""
    _attr_has_entity_name = True
    
    def __init__(self, delongh_device, hass: HomeAssistant):
        """Init entity with the device"""
        self._attr_unique_id = \
            f'{delongh_device.mac}_{self.__class__.__name__}'
        self.device: DelongiPrimadonna = delongh_device
        self.hass = hass

    @property
    def device_info(self):
        """Shared device info information"""
        return {
            'identifiers': {(DOMAIN, self.device.mac)},
            'connections': {
                (dr.CONNECTION_NETWORK_MAC, self.device.mac)
            },
            'name': self.device.name,
            'manufacturer': 'Delongi',
            'model': self.device.model
        }


def sign_request(message):
    """Request signer"""
    deviser = 0x1d0f
    for item in message[:len(message) - 2]:
        i3 = (((deviser << 8) | (deviser >> 8)) &
              0x0000ffff) ^ (item & 0xffff)
        i4 = i3 ^ ((i3 & 0xff) >> 4)
        i5 = i4 ^ ((i4 << 12) & 0x0000ffff)
        deviser = i5 ^ (((i5 & 0xff) << 5) & 0x0000ffff)
    signature = list((deviser & 0x0000ffff).to_bytes(2, byteorder='big'))
    message[len(message) - 2] = signature[0]
    message[len(message) - 1] = signature[1]
    return message


class DelongiPrimadonna:
    """Delongi Primadonna class"""

    def __init__(self, config: dict, hass: HomeAssistant) -> None:
        """Initialize device"""
        self.mac = config.get(CONF_MAC)
        self.name = config.get(CONF_NAME)
        self.hostname = ''
        self.model = 'Prima Donna'
        self.friendly_name = ''
        self.cooking = AvailableBeverage.NONE
        self._device_status = None
        self.connected = False
        self.active = False
        self._client = None
        self._hass = hass
        self._device = None

    async def disconnect(self):
        _LOGGER.info('Disconnect from %s', self.mac)
        if (self._client is not None) and self._client.is_connected:
            await self._client.disconnect()

    async def _connect(self):
        if (self._client is None) or (not self._client.is_connected):
            _LOGGER.warning('Start connection')

            scanner = bluetooth.async_get_scanner(self._hass)
            _LOGGER.warning('Got scanner')
            self._device = await bluetooth.async_ble_device_from_address(
                self.mac
            )
            _LOGGER.warning('Got device')
            if not self._device:
                raise BleakError(
                    f'A device with address {self.mac} could not be found.')

            #self._client = BleakClient(self._device)
            #_LOGGER.warning('Connect to %s %s', self.mac,
            #                self._client.is_connected)
            # await self._client.connect()
            #_LOGGER.warning('Connected')

            # await self._client.start_notify(
            #    uuid.UUID(CONTROLL_CHARACTERISTIC),
            #    self._handle_data
            #)

    def _event_trigger(self, value):
        event_data = {'data': str(hexlify(value, ' '))}

        if str(bytearray(value)) in DEVICE_NOTIFICATION:
            event_data.setdefault(
                'type',
                DEVICE_NOTIFICATION.get(str(bytearray(value))).kind)
            event_data.setdefault(
                'description',
                DEVICE_NOTIFICATION.get(str(bytearray(value))).description)

        self._hass.bus.async_fire(
            f'{DOMAIN}_event', event_data)
        _LOGGER.info('Event triggered: %s', event_data)

    def _handle_data(self, sender, value):
        if self._device_status != hexlify(value, ' '):
            _LOGGER.info('Received data: %s from %s',
                         hexlify(value, ' '), sender)
            self._event_trigger(value)
        self._device_status = hexlify(value, ' ')

    async def power_on(self) -> None:
        """Turn the device on."""
        await self._connect()
        try:
            await self._client.write_gatt_char(
                uuid.UUID(CONTROLL_CHARACTERISTIC),
                bytearray(BYTES_POWER))
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)

    async def cup_light_on(self) -> None:
        """Turn the cup light on."""
        await self._connect()
        try:
            await self._client.write_gatt_char(
                CONTROLL_CHARACTERISTIC,
                bytearray(BYTES_CUP_LIGHT_ON))
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)

    async def cup_light_off(self) -> None:
        """Turn the cup light off."""
        await self._connect()
        try:
            await self._client.write_gatt_char(
                CONTROLL_CHARACTERISTIC,
                bytearray(BYTES_CUP_LIGHT_OFF))
            _LOGGER.warning('written')
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)

    async def beverage_start(self, beverage: AvailableBeverage) -> None:
        """Start beverage"""
        await self._connect()
        try:
            await self._client.write_gatt_char(
                CONTROLL_CHARACTERISTIC,
                bytearray(BEVERAGE_COMMANDS.get(beverage).on))
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)
        finally:
            self.cooking = AvailableBeverage.NONE

    async def beverage_cancel(self) -> None:
        """Cancel beverage"""
        await self._connect()
        if self.connected and self.cooking != AvailableBeverage.NONE:
            try:
                await self._client.write_gatt_char(
                    CONTROLL_CHARACTERISTIC,
                    bytearray(BEVERAGE_COMMANDS.get(self.cooking).off))
            except BleakError as error:
                self.connected = False
                _LOGGER.warning('BleakError: %s', error)
            finally:
                self.cooking = AvailableBeverage.NONE

    async def debug(self):
        await self._connect()
        try:
            await self._client.write_gatt_char(
                uuid.UUID(CONTROLL_CHARACTERISTIC), bytearray(DEBUG))
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)

    async def get_device_name(self):
        try:
            await self._connect()
            async with BleakClient(self._device) as client:
                _LOGGER.warning('Got connection')
                self.hostname = bytes(
                    await client.read_gatt_char(
                        uuid.UUID(NAME_CHARACTERISTIC)
                    )
                ).decode('utf-8')
                _LOGGER.warning('Data read')
                await client.write_gatt_char(
                    uuid.UUID(CONTROLL_CHARACTERISTIC), bytearray(DEBUG))
                _LOGGER.warning('Data wrote')
                self.connected = True
        except BleakDBusError as error:
            self.connected = False
            _LOGGER.warning('BleakDBusError: %s', error)
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)
        except asyncio.exceptions.TimeoutError as error:
            self.connected = False
            _LOGGER.warning('TimeoutError: %s', error)

    async def select_profile(self, profile_id) -> None:
        """select a profile."""
        await self._connect()
        try:
            message = [0x0d, 0x06, 0xa9, 0xf0, profile_id, 0xd7, 0xc0]
            sign_request(message)
            _LOGGER.info('Select Profile: %s', hexlify(bytearray(message), ' '))
            await self._client.write_gatt_char(
                CONTROLL_CHARACTERISTIC,
                bytearray(message))
        except BleakError as error:
            self.connected = False
            _LOGGER.warning('BleakError: %s', error)