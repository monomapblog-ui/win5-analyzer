import asyncio
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()

DELAY = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


class RateLimitedClient:
    """レート制限・リトライ付き非同期HTTPクライアント"""

    def __init__(self, delay: float = DELAY):
        self._delay = delay
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def get(self, url: str, **kwargs) -> httpx.Response:
        await asyncio.sleep(self._delay)
        response = await self._client.get(url, **kwargs)
        response.raise_for_status()
        return response
