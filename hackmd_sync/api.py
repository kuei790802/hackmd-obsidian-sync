"""HackMD API client using only stdlib."""

import json
import time
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


class HackMDAPI:
    def __init__(self, token, base_url="https://api.hackmd.io/v1", delay=0.3):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self._last_call = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def _request(self, path, method="GET", data=None, retries=3):
        self._rate_limit()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        body = None

        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req) as resp:
                    if resp.status in (202, 204):
                        return {"_status": resp.status}
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                status = e.code
                body_text = e.read().decode()[:300]

                if status == 429 and attempt < retries - 1:
                    wait = (attempt + 1) * 2
                    logger.warning(f"Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                elif status >= 500 and attempt < retries - 1:
                    wait = (attempt + 1) * 2
                    logger.warning(f"Server error {status}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"API {method} {path}: {status} {body_text}")
                    return None
            except Exception as e:
                logger.error(f"API {method} {path}: {e}")
                return None

        return None

    def get_me(self):
        return self._request("/me")

    def list_notes(self):
        return self._request("/notes") or []

    def get_note(self, note_id):
        return self._request(f"/notes/{note_id}")

    def create_note(self, title, content, read_perm="owner", write_perm="owner"):
        return self._request(
            "/notes",
            method="POST",
            data={
                "title": title,
                "content": content,
                "readPermission": read_perm,
                "writePermission": write_perm,
            },
        )

    def update_note(self, note_id, content):
        return self._request(
            f"/notes/{note_id}", method="PATCH", data={"content": content}
        )

    def delete_note(self, note_id):
        return self._request(f"/notes/{note_id}", method="DELETE")
