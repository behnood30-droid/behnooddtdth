"""تعریف پلن‌های فروش."""
from dataclasses import dataclass


def _fa(n: int | str) -> str:
    """اعداد انگلیسی رو به فارسی تبدیل می‌کنه."""
    return str(n).translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


@dataclass
class Plan:
    id: int
    gb: int
    days: int
    price_toman: int
    price_rial: int
    label: str


PLANS: list[Plan] = [
    Plan(1, 10,  30,   120_000,   1_200_000, "۱۰ گیگ — ۱۲۰ هزار تومان"),
    Plan(2, 30,  30,   300_000,   3_000_000, "۳۰ گیگ — ۳۰۰ هزار تومان"),
    Plan(3, 50,  30,   450_000,   4_500_000, "۵۰ گیگ — ۴۵۰ هزار تومان"),
    Plan(4, 100, 30,   700_000,   7_000_000, "۱۰۰ گیگ — ۷۰۰ هزار تومان"),
    Plan(5, 200, 30, 1_600_000, 16_000_000, "۲۰۰ گیگ — ۱٬۶۰۰ هزار تومان"),
]


def get_plan(plan_id: int) -> Plan | None:
    return next((p for p in PLANS if p.id == plan_id), None)
