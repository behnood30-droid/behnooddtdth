"""پلن‌های فروش سرویس."""
from dataclasses import dataclass

from utils import fa


@dataclass(frozen=True)
class Plan:
    id: int
    gb: int
    days: int
    price_toman: int
    emoji: str
    badge: str

    @property
    def label(self) -> str:
        price_str = fa(self.price_toman)
        badge = f"  {self.badge}" if self.badge else ""
        return f"{self.emoji} {fa(self.gb)} گیگ | {fa(self.days)} روزه | {price_str} تومان{badge}"


PLANS: list[Plan] = [
    Plan(1,  10, 30,    120_000, "🟢", ""),
    Plan(2,  30, 30,    300_000, "🔵", "🔥 پرفروش"),
    Plan(3,  50, 30,    450_000, "🟣", ""),
    Plan(4, 100, 30,    700_000, "🟡", "💎 ویژه"),
    Plan(5, 200, 30,  1_600_000, "🔴", "🎁 اقتصادی"),
]


def get_plan(plan_id: int) -> Plan | None:
    return next((p for p in PLANS if p.id == plan_id), None)
