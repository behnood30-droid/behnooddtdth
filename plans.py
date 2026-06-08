"""تعریف پلن‌های فروش."""
from dataclasses import dataclass

_T = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")
_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")


def fa(n) -> str:
    """تبدیل اعداد انگلیسی به فارسی."""
    return str(n).translate(_T)


@dataclass(frozen=True)
class Plan:
    id: int
    gb: int
    days: int
    price_toman: int

    @property
    def label(self) -> str:
        return f"{_EMOJIS[self.id - 1]}  {fa(self.gb)} گیگ — {fa(f'{self.price_toman:,}')} تومان"


PLANS: list[Plan] = [
    Plan(1, 10,  30,   120_000),
    Plan(2, 30,  30,   300_000),
    Plan(3, 50,  30,   450_000),
    Plan(4, 100, 30,   700_000),
    Plan(5, 200, 30, 1_600_000),
]


def get_plan(plan_id: int) -> Plan | None:
    return next((p for p in PLANS if p.id == plan_id), None)
