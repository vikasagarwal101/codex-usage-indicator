import json
import os
import select
import subprocess
import time
from datetime import datetime
from pathlib import Path
import urllib.error
import urllib.request
import uuid

WHAM_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class APIError(Exception):
    pass


class APIAuthError(APIError):
    pass


class CodexRpc:
    def __init__(self, codex_path):
        self.codex_path = codex_path or "codex"
        self.proc = None
        self.next_id = 1

    def __enter__(self):
        env = dict(os.environ)
        env["TERM"] = "dumb"
        try:
            self.proc = subprocess.Popen(
                [self.codex_path, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError as e:
            raise APIError("Codex CLI not found") from e

        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-usage-indicator",
                    "title": "Codex Usage Indicator",
                    "version": "0.1.0",
                }
            },
        )
        self.notify("initialized")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def notify(self, method, params=None):
        msg = {"method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def request(self, method, params=None, timeout=12):
        req_id = self.next_id
        self.next_id += 1
        msg = {"id": req_id, "method": method, "params": params or {}}
        self._write(msg)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise APIError(f"Codex app-server exited early: {err.strip()}")

            remaining = max(0.1, deadline - time.monotonic())
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                continue

            line = self.proc.stdout.readline()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if payload.get("id") != req_id:
                continue
            if payload.get("error"):
                message = payload["error"].get("message", "Unknown Codex error")
                if "auth" in message.lower() or "login" in message.lower():
                    raise APIAuthError(message)
                raise APIError(message)
            return payload.get("result")

        raise APIError(f"Codex app-server request timed out: {method}")

    def _write(self, msg):
        if not self.proc or not self.proc.stdin:
            raise APIError("Codex app-server is not running")
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()


class APIClient:
    def __init__(self, codex_path="codex"):
        self.codex_path = codex_path or "codex"

    def fetch_all(self):
        try:
            data = self._fetch_wham_usage()
        except APIAuthError:
            raise
        except APIError:
            return self._fetch_cli_rpc()

        count = (data.get("rate_limit_reset_credits") or {}).get("available_count", 0)
        data["reset_credits"] = {"availableCount": count, "credits": []}
        if count:
            try:
                details = self._read_reset_credits()
                if details:
                    data["reset_credits"] = details
            except (APIError, OSError):
                pass
        return data

    def _fetch_wham_usage(self):
        token = self._read_access_token()
        req = urllib.request.Request(
            WHAM_USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "codex-usage-indicator/0.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise APIAuthError(
                    "Codex OAuth token rejected. Run 'codex login'."
                ) from e
            raise APIError(f"Codex usage API returned HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise APIError(f"Network error: {e.reason}") from e
        except TimeoutError as e:
            raise APIError("Network timeout contacting Codex usage API") from e
        except json.JSONDecodeError as e:
            raise APIError("Invalid response from Codex usage API") from e

        rate_limit = raw.get("rate_limit") or {}
        credits = raw.get("credits") or {}
        spend_control = raw.get("spend_control") or {}

        return {
            "source": "OpenAI usage API",
            "account_type": "chatgpt",
            "email": raw.get("email", ""),
            "requires_openai_auth": True,
            "plan_type": raw.get("plan_type", "unknown"),
            "limit_id": "codex",
            "limit_name": "Codex",
            "primary": self._wham_window(rate_limit.get("primary_window")),
            "secondary": self._wham_window(rate_limit.get("secondary_window")),
            "credits": {
                "has_credits": bool(credits.get("has_credits")),
                "unlimited": bool(credits.get("unlimited")),
                "balance": credits.get("balance"),
                "overage_limit_reached": bool(credits.get("overage_limit_reached")),
                "approx_local_messages": credits.get("approx_local_messages") or [],
                "approx_cloud_messages": credits.get("approx_cloud_messages") or [],
            },
            "allowed": rate_limit.get("allowed"),
            "limit_reached": rate_limit.get("limit_reached"),
            "rate_limit_reached_type": raw.get("rate_limit_reached_type"),
            "code_review_rate_limit": raw.get("code_review_rate_limit"),
            "additional_rate_limits": raw.get("additional_rate_limits"),
            "spend_control": {
                "reached": bool(spend_control.get("reached")),
                "individual_limit": spend_control.get("individual_limit"),
            },
            "rate_limit_reset_credits": raw.get("rate_limit_reset_credits") or {},
            "promo": raw.get("promo"),
            "referral_beacon": raw.get("referral_beacon"),
            "ts": datetime.now(),
        }

    def _read_access_token(self):
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        auth_path = codex_home / "auth.json"
        try:
            with auth_path.open() as f:
                auth = json.load(f)
        except FileNotFoundError as e:
            raise APIError("Codex auth file not found") from e
        except (OSError, json.JSONDecodeError) as e:
            raise APIError("Could not read Codex auth file") from e

        token = (auth.get("tokens") or {}).get("access_token") or auth.get(
            "access_token"
        )
        if not token:
            raise APIError("Codex OAuth token not found")
        return token

    def _fetch_cli_rpc(self):
        with CodexRpc(self.codex_path) as rpc:
            account_result = rpc.request("account/read", {"refreshToken": False}) or {}
            limits_result = rpc.request("account/rateLimits/read", {}, timeout=30) or {}

        account = account_result.get("account") or {}
        limits = limits_result.get("rateLimits") or {}
        primary = limits.get("primary") or None
        secondary = limits.get("secondary") or None
        credits = limits.get("credits") or {}
        plan_type = limits.get("planType") or account.get("planType") or "unknown"

        return {
            "source": "Codex CLI RPC",
            "account_type": account.get("type", "unknown"),
            "email": account.get("email", ""),
            "requires_openai_auth": account_result.get("requiresOpenaiAuth", False),
            "plan_type": plan_type,
            "limit_id": limits.get("limitId", "codex"),
            "limit_name": limits.get("limitName") or "Codex",
            "primary": self._window(primary),
            "secondary": self._window(secondary),
            "credits": {
                "has_credits": bool(credits.get("hasCredits")),
                "unlimited": bool(credits.get("unlimited")),
                "balance": credits.get("balance"),
                "overage_limit_reached": False,
                "approx_local_messages": [],
                "approx_cloud_messages": [],
            },
            "allowed": None,
            "limit_reached": None,
            "rate_limit_reached_type": limits.get("rateLimitReachedType"),
            "code_review_rate_limit": None,
            "additional_rate_limits": None,
            "spend_control": {"reached": False, "individual_limit": None},
            "rate_limit_reset_credits": {},
            "reset_credits": limits_result.get("rateLimitResetCredits") or {"availableCount": 0, "credits": []},
            "promo": None,
            "referral_beacon": None,
            "ts": datetime.now(),
        }

    def _read_reset_credits(self):
        with CodexRpc(self.codex_path) as rpc:
            result = rpc.request("account/rateLimits/read", {}, timeout=30) or {}
        return result.get("rateLimitResetCredits")

    def consume_reset(self, credit_id):
        if not isinstance(credit_id, str) or not credit_id:
            raise APIError("Select an available reset")
        with CodexRpc(self.codex_path) as rpc:
            return rpc.request(
                "account/rateLimitResetCredit/consume",
                {"idempotencyKey": str(uuid.uuid4()), "creditId": credit_id},
                timeout=30,
            ) or {}

    def _wham_window(self, raw):
        if not raw:
            return None
        duration_seconds = raw.get("limit_window_seconds")
        duration_mins = int(duration_seconds / 60) if duration_seconds else None
        return {
            "used_pct": raw.get("used_percent"),
            "duration_mins": duration_mins,
            "reset_sec": raw.get("reset_at"),
            "reset_after_seconds": raw.get("reset_after_seconds"),
        }

    def _window(self, raw):
        if not raw:
            return None
        return {
            "used_pct": raw.get("usedPercent"),
            "duration_mins": raw.get("windowDurationMins"),
            "reset_sec": raw.get("resetsAt"),
        }
