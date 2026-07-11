from enum import Enum


class MembershipTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"

    @property
    def display_name(self) -> str:
        return {"free": "기본(무료)", "premium": "프리미엄(유료)"}[self.value]
