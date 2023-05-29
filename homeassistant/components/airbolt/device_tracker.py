"""Platform for sensor integration."""
# This file shows the setup for the sensors associated with the cover.
# They are setup in the same way with the call to the async_setup_entry function
# via HA from the module __init__. Each sensor has a device_class, this tells HA how
# to display it in the UI (for know types). The unit_of_measurement property tells HA
# what the unit is, so it can display the correct range. For predefined types (such as
# battery), the unit_of_measurement should match what's expected.
import logging

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .hub import Hub, Tracker

_LOGGER = logging.getLogger(__name__)


# See cover.py for more details.
# Note how both entities for each roller sensor (battry and illuminance) are added at
# the same time to the same list. This way only a single async_add_devices call is
# required.
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    hub: Hub = hass.data[DOMAIN][config_entry.entry_id]

    new_devices = []
    for device in hub.devices:
        new_devices.append(LocationTracker(hub, hub.devices[device]))
    if new_devices:
        async_add_entities(new_devices)


# This base class shows the common properties and methods for a sensor as used in this
# example. See each sensor for further details about properties and methods that
# have been overridden.
class LocationTracker(CoordinatorEntity, TrackerEntity):
    """Base representation of a GPS tracker."""

    should_poll = False

    def __init__(self, hub: Hub, tracker: Tracker) -> None:
        """Initialize the tracker."""

        super().__init__(hub.coordinator, context=tracker.id)
        self._hub = hub
        self._tracker = tracker
        _LOGGER.debug(
            "Creating LocationTracker for %s (%s)",
            tracker.name,
            tracker.id,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data: dict[str, dict[str, bool]] = self._hub.coordinator.data
        updated = any(updated for updated in data[self._tracker.id].values())
        _LOGGER.debug("Device %s updated: %r", self._tracker.id, updated)
        if updated:
            self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this tracker."""
        return self._tracker.id

    @property
    def name(self) -> str | None:
        """Return a friendly name for this tracker entity. Since this entity is the root of the associated device, this will always return None."""
        return ""

    @property
    def has_entity_name(self) -> bool:
        """Return False to mark this entity as the root of the associated device."""
        return False

    @property
    def icon(self) -> str:
        """Icon associated with this Entity."""
        return "mdi:map-marker-account"

    @property
    def device_info(self) -> DeviceInfo:
        """Return information to link this entity with the correct device."""
        return self._tracker.build_device_info(True)

    @property
    def source_type(self) -> str:
        """Return the type of the last data point."""
        return "gps"

    @property
    def latitude(self) -> float:
        """Return the last reported latitude."""
        return self._tracker.latitude

    @property
    def longitude(self) -> float:
        """Return the last reported longitude."""
        return self._tracker.longitude

    @property
    def location_accuracy(self) -> int:
        """Return the accuracy of the last reported coordinates."""
        return self._tracker.accuracy

    @property
    def location_name(self) -> str | None:
        """Return the friendly name of the last reported coordinates, as reported by the Airbolt API."""
        return self._tracker.address
