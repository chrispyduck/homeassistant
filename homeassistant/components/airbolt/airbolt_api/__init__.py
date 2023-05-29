"""Airbolt API client."""

from .classes import (
    AccelerometerConfiguration,
    DeviceHistoryPage,
    FoundDevice,
    HistoryEntry,
    LoginResult,
    Pagination,
    SessionInfo,
    TemperatureConfiguration,
    UserInfo,
    WaterAlarmConfiguration,
)
from .client import AirboltClient

__all__ = [
    "UserInfo",
    "SessionInfo",
    "LoginResult",
    "TemperatureConfiguration",
    "AccelerometerConfiguration",
    "WaterAlarmConfiguration",
    "FoundDevice",
    "HistoryEntry",
    "Pagination",
    "DeviceHistoryPage",
    "AirboltClient",
]
