"""Small, dependency-free client for the official Browsec Desktop API."""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


API_URLS = (
    "https://d5.bmtr.org/api/",
    "https://d6.bmtr.org/api/",
    "https://browsec.com/api/",
)
IP_INFO_URLS = (
    ("https://ipapi.co/json", "country_code"),
    ("https://ipinfo.io/json", "country"),
    ("https://ipwho.is/?fields=ip,country_code", "country_code"),
)
COUNTRY_CODE_RE = re.compile(r"^[a-z]{2,3}$")

COUNTRY_NAMES = {
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "bg": "Bulgaria",
    "br": "Brazil",
    "ca": "Canada",
    "ch": "Switzerland",
    "cl": "Chile",
    "cy": "Cyprus",
    "cz": "Czech Republic",
    "de": "Germany",
    "dk": "Denmark",
    "es": "Spain",
    "fi": "Finland",
    "fr": "France",
    "gr": "Greece",
    "hk": "Hong Kong",
    "hu": "Hungary",
    "ie": "Ireland",
    "il": "Israel",
    "in": "India",
    "is": "Iceland",
    "it": "Italy",
    "jp": "Japan",
    "kr": "South Korea",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "lv": "Latvia",
    "mx": "Mexico",
    "nl": "Netherlands",
    "no": "Norway",
    "nz": "New Zealand",
    "pl": "Poland",
    "ro": "Romania",
    "rs": "Serbia",
    "ru": "Russia",
    "se": "Sweden",
    "sg": "Singapore",
    "si": "Slovenia",
    "tr": "Turkey",
    "ua": "Ukraine",
    "uk": "United Kingdom",
    "us": "United States",
    "usw": "United States (West)",
    "za": "South Africa",
}


class BrowsecAPIError(RuntimeError):
    """An expected Browsec API or network error safe to display to the user."""


@dataclass(frozen=True)
class VPNServer:
    ip: str
    xsni: str
    country_code: str
    country_name: str
    availability: float | None = None
    source_ip_lrc: int | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "countryCode": self.country_code,
            "countryName": self.country_name,
            "availability": self.availability,
        }


def _safe_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrowsecAPIError("Browsec returned an invalid response") from exc
    if not isinstance(value, dict):
        raise BrowsecAPIError("Browsec returned an unexpected response")
    return value


def _api_error_message(payload: dict[str, Any], fallback: str) -> str:
    for key in ("message", "error", "error_description", "error_code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


class BrowsecAPI:
    """Uses the same endpoints and identifying headers as Desktop 1.2.2."""

    def __init__(self, api_urls: tuple[str, ...] = API_URLS) -> None:
        self.api_urls = api_urls

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        encoded_data = (
            json.dumps(data, separators=(",", ":")).encode("utf-8")
            if data is not None
            else None
        )

        for base_url in self.api_urls:
            url = urllib.parse.urljoin(base_url, path)
            if params:
                url = f"{url}?{urllib.parse.urlencode(params)}"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Browsec-Decky/0.1.0",
                "X-Browsec-Desktop-Version": "1.2.2",
                "X-Browsec-Desktop-Platform": "linux",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            request = urllib.request.Request(
                url,
                data=encoded_data,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return _safe_json(response.read())
            except urllib.error.HTTPError as exc:
                payload = _safe_json(exc.read())
                if exc.code < 500:
                    raise BrowsecAPIError(
                        _api_error_message(payload, f"Browsec rejected the request ({exc.code})")
                    ) from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc

        raise BrowsecAPIError("Could not reach the Browsec API") from last_error

    def login(self, email: str, password: str) -> dict[str, Any]:
        email = email.strip()
        if not email or len(email) > 320 or "@" not in email:
            raise BrowsecAPIError("Enter a valid email address")
        if not password or len(password) > 1024:
            raise BrowsecAPIError("Enter your Browsec password")
        payload = self._request(
            "POST",
            "v1/authentication",
            data={"email": email, "password": password},
        )
        if "error_code" in payload:
            raise BrowsecAPIError(_api_error_message(payload, "Sign-in failed"))
        return payload

    def get_account(self, token: str) -> dict[str, Any]:
        payload = self._request("GET", "v1/account", token=token)
        if "error_code" in payload:
            raise BrowsecAPIError(
                _api_error_message(payload, "Could not refresh the Browsec account")
            )
        return payload

    def get_servers(self, token: str, user_country: str) -> dict[str, Any]:
        user_country = user_country.lower()
        if not COUNTRY_CODE_RE.fullmatch(user_country):
            user_country = "ru"
        payload = self._request(
            "GET",
            "desktop/v1/servers",
            token=token,
            params={"uc": user_country},
        )
        if "error_code" in payload:
            raise BrowsecAPIError(
                _api_error_message(payload, "Could not load VPN locations")
            )
        return payload

    def destroy_token(self, token: str) -> None:
        try:
            self._request("DELETE", "v1/authentication", token=token)
        except BrowsecAPIError:
            # Local sign-out must still succeed if the network is unavailable.
            pass

    def detect_user_country(self) -> str:
        for url, key in IP_INFO_URLS:
            try:
                request = urllib.request.Request(
                    url,
                    headers={"Accept": "application/json", "User-Agent": "Browsec-Decky/0.1.0"},
                )
                with urllib.request.urlopen(request, timeout=4) as response:
                    payload = _safe_json(response.read())
                value = payload.get(key)
                if isinstance(value, str):
                    code = value.strip().lower()
                    if COUNTRY_CODE_RE.fullmatch(code):
                        return code
            except (BrowsecAPIError, urllib.error.URLError, TimeoutError, OSError):
                continue
        return "ru"


def validate_account(account: dict[str, Any]) -> tuple[str, str, str]:
    """Return (email, access_token, xray_uuid) after strict validation."""

    if not account.get("premium"):
        raise BrowsecAPIError("Browsec Premium is required for the desktop VPN service")

    email = account.get("email")
    credentials = account.get("credentials")
    if not isinstance(email, str) or not isinstance(credentials, dict):
        raise BrowsecAPIError("The Browsec account response is incomplete")
    token = credentials.get("access_token")
    xray_uuid = credentials.get("xray_uuid")
    if not isinstance(token, str) or len(token) < 16:
        raise BrowsecAPIError("The Browsec access token is missing")
    if not isinstance(xray_uuid, str):
        raise BrowsecAPIError("The Browsec Xray credential is missing")
    try:
        import uuid

        uuid.UUID(xray_uuid)
    except (ValueError, AttributeError) as exc:
        raise BrowsecAPIError("The Browsec Xray credential is invalid") from exc
    return email, token, xray_uuid


def authentication_token(authentication: dict[str, Any]) -> str:
    """Extract the short-lived login result without assuming account shape."""

    credentials = authentication.get("credentials")
    candidates = [
        authentication.get("access_token"),
        credentials.get("access_token") if isinstance(credentials, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and len(candidate) >= 16:
            return candidate
    raise BrowsecAPIError("Browsec did not return an access token")


def normalize_servers(payload: dict[str, Any], limit_per_country: int = 5) -> dict[str, list[VPNServer]]:
    countries = payload.get("countries")
    if not isinstance(countries, dict):
        raise BrowsecAPIError("The VPN server list is incomplete")

    result: dict[str, list[VPNServer]] = {}
    for raw_code, raw_country in countries.items():
        code = str(raw_code).lower()
        if not COUNTRY_CODE_RE.fullmatch(code) or not isinstance(raw_country, dict):
            continue
        groups = raw_country.get("premium_servers")
        if not isinstance(groups, list):
            continue

        servers: list[VPNServer] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            ips = group.get("ip")
            xsnis = group.get("xsni")
            lrcs = group.get("source_ip_lrc")
            availability = group.get("availability")
            xray_availability = (
                availability.get("xray") if isinstance(availability, dict) else None
            )
            if not isinstance(ips, list) or not isinstance(xsnis, list):
                continue

            for index, raw_ip in enumerate(ips):
                if index >= len(xsnis):
                    continue
                raw_xsni = xsnis[index]
                try:
                    ip = str(ipaddress.ip_address(str(raw_ip)))
                except ValueError:
                    continue
                if not isinstance(raw_xsni, str) or not raw_xsni or len(raw_xsni) > 253:
                    continue
                if any(character.isspace() for character in raw_xsni):
                    continue
                raw_lrc = lrcs[index] if isinstance(lrcs, list) and index < len(lrcs) else None
                raw_availability = (
                    xray_availability[index]
                    if isinstance(xray_availability, list) and index < len(xray_availability)
                    else None
                )
                lrc = raw_lrc if isinstance(raw_lrc, int) else None
                latency = (
                    float(raw_availability)
                    if isinstance(raw_availability, (int, float))
                    else None
                )
                servers.append(
                    VPNServer(
                        ip=ip,
                        xsni=raw_xsni,
                        source_ip_lrc=lrc,
                        availability=latency,
                        country_code=code,
                        country_name=COUNTRY_NAMES.get(code, code.upper()),
                    )
                )

        servers.sort(
            key=lambda server: (
                server.availability is None,
                server.availability if server.availability is not None else float("inf"),
            )
        )
        if servers:
            result[code] = servers[: max(1, limit_per_country)]

    if not result:
        raise BrowsecAPIError("No Premium VPN locations were returned")
    return result
