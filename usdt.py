"""بررسی تراکنش‌های USDT BEP20 و TRC20."""
import logging
import random

import httpx

log = logging.getLogger(__name__)

USDT_BEP20_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def generate_unique_amount(base_usdt: float, network: str, db) -> float:
    """مبلغ یکتا با پسوند 0.001 تا 0.009 می‌سازه."""
    suffixes = list(range(1, 10))
    random.shuffle(suffixes)
    for s in suffixes:
        candidate = round(base_usdt + s * 0.001, 3)
        if not db.has_pending_unique(candidate, network):
            return candidate
    return round(base_usdt + random.randint(1, 9) * 0.001, 3)


async def check_bep20(address: str, api_key: str, after_ts: int) -> list[dict]:
    """تراکنش‌های ورودی USDT BEP20 بعد از after_ts."""
    url = (
        f"https://api.bscscan.com/api"
        f"?module=account&action=tokentx"
        f"&contractaddress={USDT_BEP20_CONTRACT}"
        f"&address={address}"
        f"&apikey={api_key}"
        f"&sort=desc&offset=20&page=1"
    )
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            log.warning("bscscan HTTP %d", resp.status_code)
            return []
        try:
            data = resp.json()
        except Exception:
            log.warning("bscscan invalid JSON")
            return []
    except Exception as e:
        log.warning("bscscan error: %s", e)
        return []

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
        try:
            decimals = int(tx.get("tokenDecimal", "18"))
            amount = int(tx.get("value", 0)) / 10**decimals
        except (ValueError, TypeError):
            continue
        results.append({"hash": tx["hash"], "amount": amount, "timestamp": ts})
    return results


async def check_trc20(address: str, after_ts: int) -> list[dict]:
    """تراکنش‌های ورودی USDT TRC20 بعد از after_ts."""
    url = (
        f"https://apilist.tronscan.org/api/token_trc20/transfers"
        f"?toAddress={address}"
        f"&contract_address={USDT_TRC20_CONTRACT}"
        f"&limit=20&start=0"
    )
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            log.warning("tronscan HTTP %d", resp.status_code)
            return []
        try:
            data = resp.json()
        except Exception:
            log.warning("tronscan invalid JSON")
            return []
    except Exception as e:
        log.warning("tronscan error: %s", e)
        return []

    results = []
    for tx in data.get("data", []):
        ts = tx.get("block_timestamp", 0) // 1000
        if ts < after_ts:
            continue
        token_info = tx.get("tokenInfo", {})
        try:
            decimals = int(token_info.get("tokenDecimal", "6"))
            amount = int(tx.get("amount", 0)) / 10**decimals
        except (ValueError, TypeError):
            continue
        results.append({
            "hash": tx.get("transactionHash", ""),
            "amount": amount,
            "timestamp": ts,
        })
    return results
