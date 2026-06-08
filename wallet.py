"""توابع کیف پول: قیمت USDT، تولید مبلغ یکتا، چک کردن تراکنش‌ها."""
import logging
import random

import httpx

from db import DB

log = logging.getLogger(__name__)

NOBITEX_URL = "https://api.nobitex.ir/market/stats?srcCurrency=usdt&dstCurrency=rls"
USDT_BEP20_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


async def get_usdt_price_toman() -> int:
    """قیمت لحظه‌ای تتر به تومان از Nobitex."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(NOBITEX_URL)
    data = resp.json()
    rial_str = data["stats"]["usdt-rls"]["latest"]
    return int(float(rial_str) / 10)


def generate_unique_amount(base_usdt: float, network: str, db: DB) -> float:
    """یه مبلغ یکتا با پسوند ۰.۰۰۱ تا ۰.۰۰۹ می‌سازه."""
    suffixes = list(range(1, 10))
    random.shuffle(suffixes)
    for s in suffixes:
        candidate = round(base_usdt + s * 0.001, 3)
        if not db.has_pending_unique(candidate, network):
            return candidate
    return round(base_usdt + random.randint(1, 9) * 0.001, 3)


async def check_bep20_incoming(
    address: str, api_key: str, after_ts: int
) -> list[dict]:
    """تراکنش‌های ورودی USDT BEP20 به آدرس را بعد از after_ts برمی‌گردونه."""
    url = (
        f"https://api.bscscan.com/api"
        f"?module=account&action=tokentx"
        f"&contractaddress={USDT_BEP20_CONTRACT}"
        f"&address={address}"
        f"&apikey={api_key}"
        f"&sort=desc&offset=20&page=1"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)

    data = resp.json()
    if data.get("status") != "1":
        log.debug("bscscan no results: %s", data.get("message"))
        return []

    results = []
    for tx in data.get("result", []):
        ts = int(tx.get("timeStamp", 0))
        if ts < after_ts:
            continue
        if tx.get("to", "").lower() != address.lower():
            continue
        decimals = int(tx.get("tokenDecimal", "18"))
        amount = int(tx.get("value", 0)) / 10**decimals
        results.append({
            "hash": tx["hash"],
            "amount": amount,
            "timestamp": ts,
        })
    return results


async def check_trc20_incoming(address: str, after_ts: int) -> list[dict]:
    """تراکنش‌های ورودی USDT TRC20 به آدرس را بعد از after_ts برمی‌گردونه."""
    url = (
        f"https://apilist.tronscanapi.com/api/token_trc20/transfers"
        f"?toAddress={address}&token={USDT_TRC20_CONTRACT}&limit=20&start=0"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)

    data = resp.json()
    results = []
    for tx in data.get("data", []):
        # block_timestamp در میلی‌ثانیه است
        ts = tx.get("block_timestamp", 0) // 1000
        if ts < after_ts:
            continue
        token_info = tx.get("tokenInfo", {})
        decimals = int(token_info.get("tokenDecimal", "6"))
        try:
            amount = int(tx.get("amount", 0)) / 10**decimals
        except (ValueError, TypeError):
            continue
        results.append({
            "hash": tx.get("transactionHash", ""),
            "amount": amount,
            "timestamp": ts,
        })
    return results
