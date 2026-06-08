"""ابزارهای کمکی: تاریخ شمسی، اعداد فارسی، progress bar."""
from datetime import datetime, timezone

try:
    import jdatetime
    _JDATETIME = True
except ImportError:
    _JDATETIME = False

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬،", "0123456789  ")


def fa(n) -> str:
    """عدد رو با جداکننده هزارگان فارسی برمیگردونه."""
    if isinstance(n, (int, float)):
        return f"{int(n):,}".translate(_FA)
    return str(n).translate(_FA)


def en(text: str) -> str:
    """اعداد فارسی رو به انگلیسی تبدیل میکنه."""
    return text.translate(_EN).replace(" ", "").replace(",", "")


def to_jalali(dt_input) -> str:
    """تاریخ ISO string یا datetime رو به شمسی تبدیل میکنه."""
    if not dt_input:
        return "نامشخص"
    try:
        if isinstance(dt_input, str):
            dt = datetime.fromisoformat(dt_input)
        else:
            dt = dt_input
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if _JDATETIME:
            jdt = jdatetime.datetime.fromgregorian(datetime=dt)
            return jdt.strftime("%Y/%m/%d").translate(_FA)
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return str(dt_input)[:10]


def unix_to_jalali(ts: int | None) -> str:
    """Unix timestamp رو به تاریخ شمسی تبدیل میکنه."""
    if not ts:
        return "نامشخص"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return to_jalali(dt)


def progress_bar(used: float, total: float, size: int = 10) -> str:
    """Progress bar با ▓ (مصرف) و ░ (باقیمانده)."""
    if total <= 0:
        return "░" * size
    pct = min(used / total, 1.0)
    filled = round(pct * size)
    return "▓" * filled + "░" * (size - filled)


def user_level(purchases: int) -> str:
    if purchases >= 10:
        return "🥇 Gold"
    if purchases >= 3:
        return "🥈 Silver"
    return "🥉 Bronze"


def bytes_to_gb(b: int) -> float:
    return round(b / 1_073_741_824, 2)
