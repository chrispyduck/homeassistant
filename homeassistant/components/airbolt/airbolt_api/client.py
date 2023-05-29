"""The Airbolt API client class."""

import asyncio
import logging
from urllib.parse import urljoin

from aiohttp import ClientSession
from pydantic import parse_raw_as  # pylint: disable=no-name-in-module

from .classes import DeviceHistoryPage, FoundDevice, LoginResult, UserInfo

logger: logging.Logger = logging.getLogger("airbolt_api.client")


class AirboltClient:
    """Client for interacting with the Airbolt API."""

    BASE_URL = "https://airboltapiconnect.com/api/"

    _session: ClientSession
    _login_result: LoginResult
    _username: str
    _password: str

    def __init__(self) -> None:
        """Create an uninitialized instance of the Airbolt API client. The next call should be login()."""
        self._session = ClientSession()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": "",
                "Content-Type": "application/json; charset=utf-8",
            }
        )

    async def __aenter__(self) -> "AirboltClient":
        """Allow this client instance to be used as a context manager. Handles the lifecycle of the underlying aiohttp session."""
        return self

    async def __aexit__(self, *args):
        """Allow this client instance to be used as a context manager. Handles the lifecycle of the underlying aiohttp session."""
        await self.close()

    async def close(self):
        """Close the current aiohttp session."""
        await self._session.close()

    async def _get(self, path: str) -> str:
        """Execute a HTTP GET request for the given path relative to the API root."""
        retry = True
        while retry:
            response = await self._session.get(urljoin(AirboltClient.BASE_URL, path))

            if response.status == 200:
                return await response.text()

            retry = False

            if response.status == 401:
                await asyncio.sleep(500)
                await self._reauthenticate()

        response.raise_for_status()
        return ""  # should never happen since raise_for_status raises an exception

    async def _post(self, path: str, body: dict) -> str:
        """Execute a HTTP POST request for the given path relative to the API root."""
        retry = True
        while retry:
            response = await self._session.post(
                urljoin(AirboltClient.BASE_URL, path), json=body
            )

            if response.status == 200:
                return await response.text()

            retry = False
            retry = False
            if response.status == 401:
                await asyncio.sleep(500)
                await self._reauthenticate()
                continue

        response.raise_for_status()
        return ""  # should never happen since raise_for_status raises an exception

    async def login(self, username: str, password: str) -> LoginResult:
        """Authenticate to the remote API using the given credentials."""

        self._username = username
        self._password = password

        return await self._reauthenticate()

    async def _reauthenticate(self) -> LoginResult:
        raw_response = await self._post(
            "login",
            {
                "username": self._username,
                "password": self._password,
                "twoFactorCode": "",
            },
        )
        self._login_result = LoginResult.parse_raw(raw_response)

        self._session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": self._login_result.auth_header,
            }
        )

        logger.debug("Authenticated as %s", self._login_result.username)

        return self._login_result

    async def get_user_info(self) -> UserInfo:
        """Obtain information about the logged in user."""
        raw_data = await self._get("users/me")
        return UserInfo.parse_raw(raw_data)

    async def find_devices(self) -> list[FoundDevice]:
        """Fetch a list of devices registered with this account."""
        raw_data = await self._get(
            f"devices/find/{self._login_result.id}?page=0&perPage=999"
        )
        return parse_raw_as(list[FoundDevice], raw_data)

    async def get_device_history_page(
        self, device_uuid: str, page: int = 1, page_size: int = 10
    ) -> DeviceHistoryPage:
        """Fetch a list of past check-ins for the given device."""
        raw_data = await self._get(
            f"history/find/device/{device_uuid}?page={page}&perPage={page_size}"
        )
        return DeviceHistoryPage.parse_raw(raw_data)
