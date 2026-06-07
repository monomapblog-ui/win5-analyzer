"""JRA-VAN API（有料）から払戻・オッズを収集
契約が必要: https://jra-van.jp/
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

JRAVAN_API_KEY = os.getenv("JRAVAN_API_KEY")
JRAVAN_BASE = "https://api.jra-van.jp/v1"  # 実際のエンドポイントは要確認


async def fetch_win5_payout(held_date: str) -> dict | None:
    """JRA-VANからWIN5払戻情報を取得する（YYYY-MM-DD形式）"""
    if not JRAVAN_API_KEY:
        raise EnvironmentError(
            "JRAVAN_API_KEY が設定されていません。.env を確認してください。"
        )

    url = f"{JRAVAN_BASE}/win5/payout"
    params = {"date": held_date, "api_key": JRAVAN_API_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def fetch_odds(race_id: str) -> dict | None:
    """JRA-VANからリアルタイムオッズを取得する"""
    if not JRAVAN_API_KEY:
        raise EnvironmentError(
            "JRAVAN_API_KEY が設定されていません。.env を確認してください。"
        )

    url = f"{JRAVAN_BASE}/odds/{race_id}"
    params = {"api_key": JRAVAN_API_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
