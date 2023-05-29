"""A demonstration 'hub' that connects several devices."""
from __future__ import annotations

# In a real implementation, this would be in an external library that's on PyPI.
# The PyPI package needs to be included in the `requirements` section of manifest.json
# See https://developers.home-assistant.io/docs/creating_integration_manifest
# for more information.
# This dummy hub always returns 3 rollers.
import collections
from datetime import datetime, timedelta
import logging

from aiohttp.web import HTTPClientError
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import airbolt_api as api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class Tracker:
    """Maintains state for a GPS tracker."""

    _id: str
    _name: str
    _model: str
    _hass_device: DeviceInfo
    _hass_device_pointer: DeviceInfo
    _last_report: api.HistoryEntry | None

    def __init__(self, discovered_info: api.FoundDevice) -> None:
        """Create an instance of a Tracker that represents a single Airbolt GPS device."""
        self._id = discovered_info.device_uuid
        self._name = ""
        self._model = ""
        self._last_report = None
        self.update_device(discovered_info)

    def update_device(self, discovered_info: api.FoundDevice) -> bool:
        """Update properties of this device."""
        if (
            self._name == discovered_info.name
            and self._model == discovered_info.device_type
        ):
            return False

        self._name = discovered_info.name
        self._model = discovered_info.device_type
        return True

    def update_location(self, history_entry: api.HistoryEntry) -> bool:
        """Update the tracker data from the given history entry and returns a boolean indicating whether anything changed."""
        if (
            self._last_report
            and self._last_report.time_created == history_entry.time_created
        ):
            return False

        self._last_report = history_entry
        _LOGGER.debug(
            "Updated last location for %s: %s (%f, %f)",
            self.id,
            self.name,
            self.latitude,
            self.longitude,
        )
        return True

    @property
    def id(self) -> str:
        """Unique identifier of this tracker."""
        return self._id

    @property
    def name(self) -> str:
        """Friendly name of this tracker."""
        return self._name

    @property
    def latitude(self) -> float:
        """Last reported latitude of this tracker."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.latitude

    @property
    def longitude(self) -> float:
        """Last reported longitude of this tracker."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.longitude

    @property
    def accuracy(self) -> int:
        """Accuracy (in meters) of the last reported location of this tracker."""
        if not self._last_report:
            raise MissingDataError()
        return int(self._last_report.accuracy or 10000)

    @property
    def address(self) -> str:
        """Geocoded address of the last location of this tracker."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.address

    @property
    def alert_type(self) -> str:
        """Type of last report sent by this tracker: SOS, Motion, Schedule, Water(?)."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.alert_type

    @property
    def last_report_time(self) -> datetime:
        """The timestamp of the last report from this tracker."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.time_created

    @property
    def modem_temperature(self) -> int | None:
        """Temperature of the modem when the tracker last reported."""
        if not self._last_report:
            raise MissingDataError()
        return self._last_report.modem_temperature

    def build_device_info(self, parent: bool = False) -> DeviceInfo:
        """Return a DeviceInfo instance used to relate entities under a single device."""
        if parent:
            return DeviceInfo(
                identifiers={(DOMAIN, self._id)},
                manufacturer="Airbolt",
                name=self.name,
                model=self._model,
            )

        return DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            manufacturer="Airbolt",
        )


class AirboltCoordinator(DataUpdateCoordinator):
    """Centralize fetches from Airbolt API to reduce traffic."""

    def __init__(self, hass: HomeAssistant, hub: Hub) -> None:
        """Create an instance of AirboltCoordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=self.__class__.__name__,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(minutes=5),
        )
        self._hub = hub

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            _LOGGER.debug("Beginning background update")
            async with async_timeout.timeout(10):
                # Grab active context variables to limit data required to be fetched from API
                # Note: using context is not required if there is no need or ability to limit
                # data retrieved from API.
                listening_tracker_ids: set[str] = set(self.async_contexts())
                coordinator_data: dict[str, dict[str, bool]] = collections.defaultdict(
                    dict
                )

                # discover devices
                for discovered_device in await self._hub.client.find_devices():
                    tracker_id = discovered_device.device_uuid
                    if tracker_id in self._hub.devices:
                        coordinator_data[tracker_id]["device"] = self._hub.devices[
                            tracker_id
                        ].update_device(discovered_device)
                    else:
                        # for later: notify hass of newly discovered item
                        _LOGGER.debug(
                            "Discovered new device %s: %s",
                            tracker_id,
                            discovered_device.name,
                        )
                        self._hub.devices[tracker_id] = Tracker(discovered_device)

                # update trackers that are listening for updates
                for tracker_id in listening_tracker_ids:
                    tracker = self._hub.devices[tracker_id]
                    page = await self._hub.client.get_device_history_page(
                        tracker.id, page=1, page_size=1
                    )
                    if page.success:
                        coordinator_data[tracker_id]["location"] = tracker.update(
                            page.data[0]
                        )

                return coordinator_data
        # except ApiAuthError as err:
        #    # Raising ConfigEntryAuthFailed will cancel future updates
        #    # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #    raise ConfigEntryAuthFailed from err
        except Exception as exc:
            raise UpdateFailed("Error communicating with API") from exc


class Hub:
    """Dummy hub for Hello World example."""

    manufacturer = "Airbolt"

    _coordinator: AirboltCoordinator
    _hass: HomeAssistant
    _client: api.AirboltClient
    _user: api.UserInfo
    _devices: dict[str, Tracker] = {}

    def __init__(self, hass: HomeAssistant) -> None:
        """Init dummy hub."""
        self._hass = hass
        self._client = api.AirboltClient()
        self._coordinator = AirboltCoordinator(hass, self)

    async def close(self):
        """Clean up this hub instance."""
        await self._client.close()

    async def _login(self, username: str, password: str) -> None:
        try:
            user = await self._client.login(username, password)
            self._user = user
        except HTTPClientError as client_error:
            _LOGGER.warning(
                "Login failed for %s: %s",
                username,
                client_error.reason,
                exc_info=client_error,
            )
            raise InvalidCredentials from client_error

    async def verify_credentials(self, username: str, password: str) -> None:
        """Verify that the user's credentials are valid."""
        await self._login(username, password)

    async def start(self, username: str, password: str) -> None:
        """Authenticate and fetches information required to start this integration."""
        _LOGGER.debug("Authenticating to Airbolt API as %s", username)
        await self._login(username, password)
        for discovered_device in await self._client.find_devices():
            _LOGGER.debug(
                "Found device %s: %s",
                discovered_device.device_uuid,
                discovered_device.name,
            )
            device_history = await self._client.get_device_history_page(
                discovered_device.device_uuid, page=1, page_size=1
            )
            last_position = device_history.data[0] if device_history.success else None
            known_device = Tracker(discovered_device)
            if last_position:
                known_device.update_location(last_position)
            self._devices[known_device.id] = known_device

    @property
    def client(self) -> api.AirboltClient:
        """Return the Airbolt API client instance."""
        return self._client

    @property
    def coordinator(self) -> DataUpdateCoordinator:
        """Fetches the coordinator instance used to coordinate updates."""
        return self._coordinator

    @property
    def hub_id(self) -> str:
        """Unique ID for this hub instance."""
        return self._user.id

    @property
    def name(self) -> str:
        """Friendly name for this account."""
        return f"{self._user.name} ({self._user.username})"

    @property
    def devices(self) -> dict[str, Tracker]:
        """Returns a list of known devices."""
        return self._devices


class InvalidCredentials(Exception):
    """Invalid username or password."""


class MissingDataError(Exception):
    """Data required for the plugin to function is missing."""
