"""Third-party emote provider (BTTV, FFZ, 7TV)

Fetches emote sets from third-party services and detects
emote names in chat message text for inline image rendering.
"""
import re
import time
import logging
import threading
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_CACHE_TTL = 30 * 60  # 30 minutes


def build_emote_url(source: str, emote_id: str) -> str:
    """Build CDN URL for emote image by source provider."""
    if source == "bttv":
        return f"https://cdn.betterttv.net/emote/{emote_id}/2x"
    elif source == "ffz":
        return f"https://cdn.frankerfacez.com/emote/{emote_id}/2"
    elif source == "7tv":
        return f"https://cdn.7tv.app/emote/{emote_id}/2x.webp"
    return f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/static/light/1.0"


class EmoteProvider:
    """BTTV/FFZ/7TV emote fetcher and text-based detector."""

    def __init__(self) -> None:
        self._emote_map: Dict[str, Dict] = {}  # name -> {id, source, url}
        self._last_fetch_time: float = 0
        self._channel_id: Optional[str] = None
        self._loading: bool = False

    @property
    def emote_count(self) -> int:
        return len(self._emote_map)

    def set_channel_id(self, channel_id: str) -> None:
        """Set the Twitch channel ID for channel-specific emote fetching."""
        self._channel_id = channel_id

    def is_stale(self) -> bool:
        return time.time() - self._last_fetch_time > _CACHE_TTL

    def load_emotes(self) -> None:
        """Fetch emotes from all providers (blocking - call from background thread)."""
        if self._loading:
            return
        self._loading = True
        try:
            new_map: Dict[str, Dict] = {}

            # Global emotes
            self._fetch_bttv_global(new_map)
            self._fetch_ffz_global(new_map)
            self._fetch_7tv_global(new_map)

            # Channel-specific emotes
            if self._channel_id:
                self._fetch_bttv_channel(new_map)
                self._fetch_ffz_channel(new_map)
                self._fetch_7tv_channel(new_map)

            self._emote_map = new_map
            self._last_fetch_time = time.time()
            logger.info(f"Loaded {len(new_map)} third-party emotes"
                        f" (channel_id={self._channel_id})")
        except Exception as e:
            logger.error(f"Failed to load third-party emotes: {e}")
        finally:
            self._loading = False

    def refresh_if_stale(self) -> None:
        """Trigger background refresh if cache is stale."""
        if self.is_stale() and not self._loading:
            threading.Thread(
                target=self.load_emotes, daemon=True
            ).start()

    def detect_emotes(
        self,
        text: str,
        twitch_positions: List[Tuple[int, int]],
    ) -> List[Dict]:
        """Detect third-party emotes in message text.

        Args:
            text: Original message text.
            twitch_positions: List of (start, end_exclusive) positions
                already occupied by Twitch native emotes.

        Returns:
            List of emote dicts with id, start, end (inclusive), name, source, url.
        """
        if not self._emote_map:
            return []

        # Build set of occupied character indices
        occupied: set = set()
        for start, end in twitch_positions:
            for i in range(start, end):
                occupied.add(i)

        results: List[Dict] = []

        # Match each whitespace-delimited token against emote names
        for match in re.finditer(r'\S+', text):
            word = match.group()
            start = match.start()
            end = match.end() - 1  # inclusive

            if word in self._emote_map:
                # Skip if overlapping with Twitch emotes
                if any(i in occupied for i in range(start, end + 1)):
                    continue

                emote_data = self._emote_map[word]
                results.append({
                    "id": emote_data["id"],
                    "start": start,
                    "end": end,
                    "name": word,
                    "source": emote_data["source"],
                    "url": emote_data["url"],
                })
                # Mark positions as occupied
                for i in range(start, end + 1):
                    occupied.add(i)

        results.sort(key=lambda e: e["start"])
        return results

    # ── BTTV ─────────────────────────────────────────────

    def _fetch_bttv_global(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                "https://api.betterttv.net/3/cached/emotes/global",
                timeout=10,
            )
            resp.raise_for_status()
            for emote in resp.json():
                emote_id = emote["id"]
                code = emote["code"]
                emote_map[code] = {
                    "id": emote_id,
                    "source": "bttv",
                    "url": build_emote_url("bttv", emote_id),
                }
            logger.debug(f"BTTV global: {len(resp.json())} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch BTTV global emotes: {e}")

    def _fetch_bttv_channel(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                f"https://api.betterttv.net/3/cached/users/twitch/{self._channel_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("BTTV: channel not registered")
                return
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for emote in data.get("channelEmotes", []) + data.get("sharedEmotes", []):
                emote_id = emote["id"]
                code = emote["code"]
                emote_map[code] = {
                    "id": emote_id,
                    "source": "bttv",
                    "url": build_emote_url("bttv", emote_id),
                }
                count += 1
            logger.debug(f"BTTV channel: {count} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch BTTV channel emotes: {e}")

    # ── FFZ ──────────────────────────────────────────────

    def _fetch_ffz_global(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                "https://api.frankerfacez.com/v1/set/global",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for _set_id, emote_set in data.get("sets", {}).items():
                for emote in emote_set.get("emoticons", []):
                    emote_id = str(emote["id"])
                    name = emote["name"]
                    emote_map[name] = {
                        "id": emote_id,
                        "source": "ffz",
                        "url": build_emote_url("ffz", emote_id),
                    }
                    count += 1
            logger.debug(f"FFZ global: {count} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch FFZ global emotes: {e}")

    def _fetch_ffz_channel(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                f"https://api.frankerfacez.com/v1/room/id/{self._channel_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("FFZ: channel not registered")
                return
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for _set_id, emote_set in data.get("sets", {}).items():
                for emote in emote_set.get("emoticons", []):
                    emote_id = str(emote["id"])
                    name = emote["name"]
                    emote_map[name] = {
                        "id": emote_id,
                        "source": "ffz",
                        "url": build_emote_url("ffz", emote_id),
                    }
                    count += 1
            logger.debug(f"FFZ channel: {count} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch FFZ channel emotes: {e}")

    # ── 7TV ──────────────────────────────────────────────

    def _fetch_7tv_global(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                "https://7tv.io/v3/emote-sets/global",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            count = 0
            for emote in data.get("emotes", []):
                emote_id = emote["id"]
                name = emote["name"]
                url = self._build_7tv_url(emote)
                emote_map[name] = {
                    "id": emote_id,
                    "source": "7tv",
                    "url": url,
                }
                count += 1
            logger.debug(f"7TV global: {count} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch 7TV global emotes: {e}")

    def _fetch_7tv_channel(self, emote_map: Dict) -> None:
        try:
            resp = requests.get(
                f"https://7tv.io/v3/users/twitch/{self._channel_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("7TV: channel not registered")
                return
            resp.raise_for_status()
            data = resp.json()
            emote_set = data.get("emote_set", {})
            count = 0
            for emote in emote_set.get("emotes", []):
                emote_id = emote["id"]
                name = emote["name"]  # Channel alias
                url = self._build_7tv_url(emote)
                emote_map[name] = {
                    "id": emote_id,
                    "source": "7tv",
                    "url": url,
                }
                count += 1
            logger.debug(f"7TV channel: {count} emotes")
        except Exception as e:
            logger.warning(f"Failed to fetch 7TV channel emotes: {e}")

    @staticmethod
    def _build_7tv_url(emote: Dict) -> str:
        """Build 7TV CDN URL from emote data, falling back to default pattern."""
        host = emote.get("data", {}).get("host", {})
        url_base = host.get("url", "")
        if url_base.startswith("//"):
            url_base = "https:" + url_base
        if url_base:
            return f"{url_base}/2x.webp"
        return build_emote_url("7tv", emote.get("id", ""))
