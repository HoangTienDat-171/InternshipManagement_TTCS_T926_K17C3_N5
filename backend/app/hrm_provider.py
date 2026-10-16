"""Loopback-only HTTP adapter for the isolated HRM demonstration service."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_EMPLOYEES = 5000
MAX_PAGES = 100


class HRMProviderError(RuntimeError):
    """Safe provider error that never carries a request header or response body."""

    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


@dataclass(frozen=True)
class HRMSandboxConfig:
    base_url: str
    api_key: str
    timeout_seconds: float

    @property
    def display_endpoint(self) -> str:
        parsed = urlsplit(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"


def get_sandbox_config() -> tuple[HRMSandboxConfig | None, str | None]:
    provider = os.getenv("HRM_PROVIDER", "").strip().casefold()
    base_url = os.getenv("HRM_SANDBOX_BASE_URL", "").strip()
    api_key = os.getenv("HRM_SANDBOX_API_KEY", "")
    if provider != "sandbox" or not base_url or not api_key:
        return None, None
    if len(api_key) < 32 or len(api_key) > 256 or any(ord(char) < 33 or ord(char) > 126 for char in api_key):
        return None, "HRM_SANDBOX_API_KEY phải là credential thử nghiệm ngẫu nhiên tối thiểu 32 ký tự ASCII."

    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"}:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError
        if hostname.casefold() != "localhost":
            if not ipaddress.ip_address(hostname).is_loopback:
                raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        return None, "HRM Sandbox chỉ được cấu hình bằng URL loopback HTTP(S) hợp lệ."

    try:
        timeout = float(os.getenv("HRM_SANDBOX_TIMEOUT_SECONDS", "5"))
    except ValueError:
        timeout = 5
    timeout = min(max(timeout, 1), 15)
    return HRMSandboxConfig(base_url.rstrip("/"), api_key, timeout), None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HRMSandboxProvider:
    provider_name = "HRM Sandbox"
    provider_id = "sandbox"

    def __init__(self, config: HRMSandboxConfig, connection_id: str = "sandbox"):
        self.config = config
        self.provider_id = connection_id
        self._opener = build_opener(_NoRedirect)

    def _read_json(self, path: str) -> dict:
        url = f"{self.config.base_url}/api/v1/{path.lstrip('/')}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "User-Agent": "IMS-HRM-Sandbox-Adapter/1.0",
            },
            method="GET",
        )
        for attempt in range(2):
            try:
                with self._opener.open(request, timeout=self.config.timeout_seconds) as response:
                    if response.status != 200:
                        raise HRMProviderError("HRM Sandbox trả về trạng thái không thành công.")
                    length = response.headers.get("Content-Length")
                    if length and int(length) > MAX_RESPONSE_BYTES:
                        raise HRMProviderError("Phản hồi HRM Sandbox vượt quá giới hạn cho phép.")
                    body = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise HRMProviderError("Phản hồi HRM Sandbox vượt quá giới hạn cho phép.")
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise HRMProviderError("Định dạng phản hồi HRM Sandbox không hợp lệ.")
                return payload
            except HTTPError as exc:
                if exc.code in {429, 502, 503, 504} and attempt == 0:
                    time.sleep(0.2)
                    continue
                if exc.code == 401:
                    raise HRMProviderError("HRM Sandbox từ chối xác thực; hãy kiểm tra cấu hình local.") from None
                if 300 <= exc.code < 400:
                    raise HRMProviderError("HRM Sandbox không được chuyển hướng tới endpoint khác.") from None
                raise HRMProviderError(f"HRM Sandbox trả về HTTP {exc.code}.") from None
            except (URLError, TimeoutError, OSError):
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise HRMProviderError("Không kết nối được HRM Sandbox trong thời gian cho phép.") from None
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                raise HRMProviderError("Phản hồi HRM Sandbox không phải JSON hợp lệ.") from None
        raise HRMProviderError("Không kết nối được HRM Sandbox.")

    async def _get_json(self, path: str) -> dict:
        return await asyncio.to_thread(self._read_json, path)

    async def test_connection(self) -> None:
        payload = await self._get_json("health")
        # Sandbox installation identity is separate from the IMS source scope.
        if payload.get("status") != "ok" or payload.get("provider_id") != "sandbox":
            raise HRMProviderError("Dịch vụ phản hồi không đúng contract HRM Sandbox.")

    async def fetch_employees(self) -> list[dict]:
        employees: list[dict] = []
        page = 1
        while page <= MAX_PAGES:
            payload = await self._get_json(f"employees?page={page}&page_size=50")
            items = payload.get("items")
            if not isinstance(items, list):
                raise HRMProviderError("Danh sách nhân viên HRM Sandbox không hợp lệ.")
            total_pages = payload.get("total_pages")
            if not isinstance(total_pages, int) or total_pages < 0 or total_pages > MAX_PAGES:
                raise HRMProviderError("Thông tin phân trang HRM Sandbox không hợp lệ.")
            if payload.get("page") != page:
                raise HRMProviderError("HRM Sandbox trả sai trang dữ liệu.")
            for item in items:
                if not isinstance(item, dict):
                    employees.append({})
                    continue
                employees.append({
                    "external_employee_id": item.get("employee_id"),
                    "full_name": item.get("full_name"),
                    "work_email": item.get("work_email"),
                    "phone": item.get("phone"),
                    "department_code": item.get("department_code"),
                    "department": item.get("department_name"),
                    "job_title": item.get("job_title"),
                    "employment_status": str(item.get("employment_status") or "").casefold(),
                    "source_updated_at": item.get("updated_at"),
                })
                if len(employees) > MAX_EMPLOYEES:
                    raise HRMProviderError("HRM Sandbox vượt quá giới hạn số nhân viên mỗi lần đồng bộ.")
            if page >= total_pages:
                return employees
            page += 1
        raise HRMProviderError("HRM Sandbox vượt quá giới hạn phân trang.")

    def _write_json_once(self, path: str, payload: dict) -> dict:
        url = f"{self.config.base_url}/api/v1/{path.lstrip('/')}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "User-Agent": "IMS-HRM-Sandbox-Adapter/1.0",
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.config.timeout_seconds) as response:
                if response.status not in {200, 201}:
                    raise HRMProviderError("HRM Sandbox rejected the candidate request.")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise HRMProviderError("HRM Sandbox response exceeded the allowed size.", uncertain=True)
            result = json.loads(body.decode("utf-8"))
            if not isinstance(result, dict):
                raise HRMProviderError("HRM Sandbox returned an invalid candidate response.", uncertain=True)
            return result
        except HTTPError as exc:
            if exc.code == 401:
                raise HRMProviderError("HRM Sandbox rejected local authentication.") from None
            if exc.code in {400, 404, 409, 422}:
                raise HRMProviderError(f"HRM Sandbox rejected the candidate request (HTTP {exc.code}).") from None
            raise HRMProviderError(f"HRM Sandbox returned HTTP {exc.code} during candidate submission.", uncertain=True) from None
        except (URLError, TimeoutError, OSError):
            raise HRMProviderError("Candidate submission outcome is uncertain; reconcile by IMS reference before retrying.", uncertain=True) from None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise HRMProviderError("Candidate submission response was invalid; reconcile by IMS reference before retrying.", uncertain=True) from None

    async def submit_candidate_request(self, payload: dict) -> dict:
        return await asyncio.to_thread(self._write_json_once, "candidate-requests", payload)

    async def fetch_candidate_requests(self, status: str = "PENDING") -> list[dict]:
        result = await self._get_json(f"candidate-requests?status={status}&page=1&page_size=100")
        items = result.get("items")
        if not isinstance(items, list) or len(items) > 100:
            raise HRMProviderError("HRM Sandbox candidate inbox response is invalid.")
        return [item for item in items if isinstance(item, dict)]

    async def get_candidate_request(self, external_reference: str) -> dict | None:
        try:
            return await self._get_json(f"candidate-requests/by-reference/{external_reference}")
        except HRMProviderError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    async def decide_candidate_request(self, external_reference: str, decision: str, reason: str | None = None) -> dict:
        payload = {"decision": decision}
        if reason:
            payload["reason"] = reason
        path = f"candidate-requests/by-reference/{external_reference}/decision"
        return await asyncio.to_thread(self._write_json_once, path, payload)


def configured_provider() -> tuple[HRMSandboxProvider | None, str | None]:
    config, error = get_sandbox_config()
    return (HRMSandboxProvider(config) if config else None), error
