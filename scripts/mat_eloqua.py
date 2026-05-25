"""
mat_eloqua.py — Oracle Eloqua MAT Wrapper
==========================================
Handles OAuth 2.0 Authorization Code flow + refresh token rotation.
Eloqua does NOT support client_credentials — ignore any code that uses that grant type.

Two-phase setup:
    Phase 1 (once, manual): Run get_authorization_url() → open in browser → user logs in
                            → Eloqua redirects to redirect_uri with ?code=...
                            → Call exchange_code_for_tokens(code) → store refresh_token securely

    Phase 2 (automated): On every Lambda cold-start, call refresh_access_token()
                         Access tokens expire in 8 hours.
                         Refresh tokens expire in 1 year OR immediately after use — whichever comes first.
                         Eloqua ALWAYS issues a new refresh token when you use one. Store it every time.

Environment variables:
    ELOQUA_BASE_URL          e.g. https://secure.p04.eloqua.com
    ELOQUA_CLIENT_ID         from your OAuth app registration
    ELOQUA_CLIENT_SECRET     from your OAuth app registration
    ELOQUA_REDIRECT_URI      must match exactly what's registered in Eloqua
    ELOQUA_REFRESH_TOKEN     store after first manual auth — rotate on each refresh

Usage (automated, after first-time setup):
    from mat_eloqua import EloquaConnector

    mat = EloquaConnector()
    mat.refresh_access_token()          # get fresh access token using stored refresh token
    contacts = mat.get_updated_contacts(since="2025-01-01T00:00:00Z")
    mat.update_contact("12345", {"fieldValues": [...]})
"""

import base64
import logging
import os
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=False)

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# ── Exceptions ────────────────────────────────────────────────────────────────

class EloquaError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response

class EloquaAuthError(EloquaError):
    """Token expired, invalid, or refresh failed."""
    pass

class EloquaNotFoundError(EloquaError):
    pass

class EloquaRateLimitError(EloquaError):
    pass


# ── Connector ─────────────────────────────────────────────────────────────────

class EloquaConnector:
    """
    Oracle Eloqua REST API connector.

    Eloqua OAuth flows:
        - grant_type=authorization_code  → exchange auth code for tokens (one-time)
        - grant_type=refresh_token       → get new access token (automated)
        - grant_type=client_credentials  → NOT SUPPORTED by Eloqua

    The token endpoint is at login.eloqua.com, not at your instance URL.
    """

    TOKEN_URL = "https://login.eloqua.com/auth/oauth2/token"
    AUTH_URL  = "https://login.eloqua.com/auth/oauth2/authorize"

    def __init__(self):
        self.base_url      = os.getenv("ELOQUA_BASE_URL", "").rstrip("/")
        self.client_id     = os.getenv("ELOQUA_CLIENT_ID", "")
        self.client_secret = os.getenv("ELOQUA_CLIENT_SECRET", "")
        self.redirect_uri  = os.getenv("ELOQUA_REDIRECT_URI", "")
        self.access_token: str | None = None
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

        if not all([self.base_url, self.client_id, self.client_secret, self.redirect_uri]):
            raise EloquaError(
                "Missing required env vars: ELOQUA_BASE_URL, ELOQUA_CLIENT_ID, "
                "ELOQUA_CLIENT_SECRET, ELOQUA_REDIRECT_URI"
            )

    # ── Phase 1: One-time manual setup ───────────────────────────────────────

    def get_authorization_url(self, state: str = "nexus") -> str:
        """
        Step 1 of first-time setup.
        Open this URL in a browser. User logs into Eloqua.
        Eloqua redirects to redirect_uri with ?code=AUTH_CODE&state=...
        Pass that AUTH_CODE to exchange_code_for_tokens().
        """
        params = {
            "response_type": "code",
            "client_id":     self.client_id,
            "redirect_uri":  self.redirect_uri,
            "state":         state,
            "scope":         "full",
        }
        url = f"{self.AUTH_URL}?{urlencode(params)}"
        print(f"\nOpen this URL in your browser:\n{url}\n")
        print("After login, Eloqua redirects to your redirect_uri with ?code=...")
        print("Copy that code and pass it to exchange_code_for_tokens(code)\n")
        return url

    def exchange_code_for_tokens(self, auth_code: str) -> dict:
        """
        Step 2 of first-time setup. One-time operation.
        Call this with the code from the browser redirect.
        Store the refresh_token in AWS Secrets Manager / .env / Parameter Store.
        NEVER store it in code or logs.

        Returns: {"access_token": ..., "refresh_token": ..., "expires_in": ...}

        Per Eloqua docs: credentials go in Basic Auth header as base64(client_id:client_secret).
        Passing client_id/client_secret in the body is explicitly NOT supported.
        Authorization codes expire in 60 seconds — call this immediately after receiving the code.
        """
        encoded = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type":  "application/json",
            },
            json={
                "grant_type":   "authorization_code",
                "code":         auth_code,
                "redirect_uri": self.redirect_uri,
            },
            verify=False
        )

        if resp.status_code != 200:
            print(resp.status_code)
            print(resp.text)
            raise EloquaAuthError(f"Token exchange failed: {resp.status_code} {resp.text}", resp.status_code)

        tokens = resp.json()
        refresh_token = tokens.get("refresh_token")
        access_token  = tokens.get("access_token")

        if not refresh_token or not access_token:
            raise EloquaAuthError(f"No tokens in response: {tokens}")

        self.access_token = access_token
        self._session.headers["Authorization"] = f"Bearer {access_token}"

        print("\nTokens received. Store this refresh_token securely:")
        print(f"  ELOQUA_REFRESH_TOKEN={refresh_token}\n")
        print("DO NOT log or commit this value. Add it to .env or AWS Secrets Manager.")

        logger.info("exchange_code_for_tokens: success")
        return tokens

    # ── Phase 2: Automated token refresh ──────────────────────────────────────

    def refresh_access_token(self, refresh_token: str | None = None) -> str:
        """
        Gets a new access token using the stored refresh token.
        Call this on every Lambda cold-start, or when you get a 401.

        Args:
            refresh_token: override — if None, reads from ELOQUA_REFRESH_TOKEN env var

        Returns: new access_token string
        """
        token = refresh_token or os.getenv("ELOQUA_REFRESH_TOKEN", "")
        if not token:
            raise EloquaAuthError(
                "No refresh token. Run get_authorization_url() → exchange_code_for_tokens() first."
            )

        # Per Eloqua docs: credentials in Basic Auth header, NOT in the body.
        # Refresh tokens expire immediately after use — Eloqua always issues a new one.
        # The old token stops working the moment you call this. Store the new one.
        encoded = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type":  "application/json",
            },
            json={
                "grant_type":    "refresh_token",
                "refresh_token": token,
                "scope":         "full",
                "redirect_uri":  self.redirect_uri,
            },
            verify=False
        )

        if resp.status_code == 401:
            raise EloquaAuthError("Refresh token rejected — re-run initial auth flow", 401)
        if resp.status_code != 200:
            print(resp.status_code)
            print(resp.text)
            raise EloquaAuthError(f"Token refresh failed: {resp.status_code} {resp.text}", resp.status_code)

        tokens = resp.json()
        self.access_token = tokens["access_token"]
        self._session.headers["Authorization"] = f"Bearer {self.access_token}"

        # Eloqua ALWAYS rotates the refresh token — the old one is now dead.
        # You must update your secret store every single time this runs.
        new_refresh = tokens.get("refresh_token")
        if new_refresh:
            logger.warning(
                "Eloqua issued a new refresh_token — update ELOQUA_REFRESH_TOKEN in "
                "Secrets Manager / .env immediately. The old token is now invalid."
            )
            print(f"\nNew refresh token — update your secret store NOW:\n  ELOQUA_REFRESH_TOKEN={new_refresh}\n")

        logger.info("refresh_access_token: access token refreshed")
        return self.access_token

    # ── Internal HTTP ──────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        params: dict | None = None,
        retries: int = 3,
    ) -> Any:
        if not self.access_token:
            raise EloquaAuthError("No access token. Call refresh_access_token() first.")

        url = f"{self.base_url}{path}"
        for attempt in range(1, retries + 1):
            try:
                resp = self._session.request(method=method, url=url, json=payload, params=params, timeout=30)

                if resp.status_code == 401:
                    raise EloquaAuthError("Access token expired — call refresh_access_token()", 401)
                if resp.status_code == 404:
                    raise EloquaNotFoundError(f"Not found: {path}", 404)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 10))
                    logger.warning(f"Rate limited — sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    raise EloquaError(f"Eloqua server error {resp.status_code}", resp.status_code)

                resp.raise_for_status()
                return resp.json() if resp.content else {}

            except (EloquaAuthError, EloquaNotFoundError):
                raise
            except Exception as e:
                if attempt >= retries:
                    raise EloquaError(f"Request failed after {retries} attempts: {e}")
                wait = attempt * 2
                logger.warning(f"Attempt {attempt}/{retries} failed: {e} — retrying in {wait}s")
                time.sleep(wait)

    # ── Contacts API ──────────────────────────────────────────────────────────

    def get_updated_contacts(self, since: str, page_size: int = 200) -> list[dict]:
        """
        Polls for contacts updated since a given ISO timestamp.
        Uses Eloqua's bulk/2.0 export API for volume fetching.

        Args:
            since: ISO timestamp e.g. "2025-01-01T00:00:00Z"
            page_size: records per page (max 50000 for bulk, use 200 for REST)

        Returns: list of contact dicts
        """
        contacts = []
        page = 1
        while True:
            resp = self._request(
                "GET",
                "/api/rest/2.0/contacts",
                params={
                    "count":         page_size,
                    "page":          page,
                    "orderBy":       "updatedAt ASC",
                    "lastUpdatedAt": since,
                },
            )
            batch = resp.get("elements", [])
            contacts.extend(batch)
            if len(batch) < page_size:
                break
            page += 1

        logger.info(f"get_updated_contacts: {len(contacts)} contacts since {since}")
        return contacts

    def get_contact(self, contact_id: str) -> dict | None:
        """Fetch a single contact by Eloqua contact ID."""
        try:
            return self._request("GET", f"/api/rest/2.0/contacts/{contact_id}")
        except EloquaNotFoundError:
            return None

    def update_contact(self, contact_id: str, fields: dict) -> dict:
        """
        Update a contact's fields.
        For custom fields, pass fieldValues as a list of {id, value} dicts.

        Example:
            mat.update_contact("12345", {
                "fieldValues": [
                    {"id": "100123", "value": "MEL_CLASSIFICATION"},  # current_stage
                    {"id": "100456", "value": "High"},                 # mel_tier
                ]
            })
        """
        return self._request("PUT", f"/api/rest/2.0/contacts/{contact_id}", payload=fields)

    def create_contact(self, fields: dict) -> dict:
        """Create a new contact in Eloqua."""
        return self._request("POST", "/api/rest/2.0/contacts", payload=fields)

    def get_contact_activities(self, contact_id: str, activity_type: str = "formSubmit") -> list[dict]:
        """
        Fetch contact activities (form fills, email clicks, etc.).
        activity_type options: formSubmit, emailOpen, emailClickthrough, webVisit
        """
        resp = self._request(
            "GET",
            f"/api/rest/2.0/activities",
            params={"type": activity_type, "contactId": contact_id, "count": 100},
        )
        return resp.get("elements", [])

    # ── Health check ─────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Verify credentials and connectivity. Safe to call from Lambda warm-up."""
        try:
            self._request("GET", "/api/rest/2.0/contacts", params={"count": 1})
            logger.info("Eloqua health check: OK")
            return True
        except EloquaAuthError as e:
            logger.error(f"Eloqua health check: AUTH FAILED — {e}")
            return False
        except Exception as e:
            logger.error(f"Eloqua health check: FAILED — {e}")
            return False


# ── First-time setup helper ───────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run this script directly to kick off the one-time authorization flow.

    1. Fill in .env with ELOQUA_CLIENT_ID, ELOQUA_CLIENT_SECRET,
       ELOQUA_REDIRECT_URI, ELOQUA_BASE_URL
    2. python mat_eloqua.py
    3. Open the printed URL in a browser
    4. Log in with your Eloqua credentials
    5. Copy the ?code= param from the redirect URL
    6. Paste it below (or the script will prompt for it)
    7. Copy the printed ELOQUA_REFRESH_TOKEN into .env / Secrets Manager
    """
    import sys

    # connector = EloquaConnector()
    # connector.get_authorization_url()

    # code = input("Paste the auth code from the redirect URL: ").strip()
    # if not code:
    #     print("No code provided — exiting.")
    #     sys.exit(1)

    # tokens = connector.exchange_code_for_tokens(code)
    # print("\nSetup complete. Add ELOQUA_REFRESH_TOKEN to your secret store.")
    # print("After that, automated runs call: connector.refresh_access_token()")
    # connector.refresh_access_token()
    # c = connector.get_updated_contacts(since='2026-04-01T00:00:00Z')
    # print(len(c))

    # resp = requests.get(
    #     "https://login.eloqua.com/id",
    #     headers={"Authorization": f"Bearer {connector.access_token}"},
    #     verify=False
    #     )
    # print(resp.json())

    import requests
    import base64

    client_id = "fccb3629-b677-4ea8-a577-6c9f9ba8519c"
    client_secret = "1COn0GLU0HE67VXfiUL2yftKKmelywzl8Y0SN0HXVzaZLURWS~BZ9Dti8nFzhFjlAJP2Sip0KDqGxCEEXtJNwzaLsqvbu8YdVgF4"

    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    resp = requests.get(
        "https://login.eloqua.com/id",
        headers={"Authorization": f"Basic {encoded}"},
        verify=False
    )
    print(resp.status_code)
    print(resp.json())