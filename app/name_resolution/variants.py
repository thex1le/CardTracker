from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.name_resolution.normalizer import normalize_name


class PlayerSearchVariant(Base):
    __tablename__ = "player_search_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    variant: Mapped[str] = mapped_column(String(300), index=True)
    variant_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(default=func.now())


def generate_typo_variants(name: str) -> list[str]:
    """Generate known-bad search variants for a player name.

    Used to find misspelled eBay listings proactively.
    Returns list of variant strings (deduplicated, excludes original).
    """
    normalized = normalize_name(name)
    parts = normalized.split()
    if len(parts) < 2:
        return []

    first = parts[0]
    last = " ".join(parts[1:])
    variants: set[str] = set()

    # 1. Drop suffix: remove Jr/Sr/II/III if present in original
    import re
    stripped = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\s*$", "", name.lower().strip()).strip()
    stripped_norm = normalize_name(stripped)
    if stripped_norm != normalized:
        variants.add(stripped_norm)

    # 2. Accent stripping is already handled by normalize_name, but generate
    # the accented version's ASCII form explicitly
    # (this catches cases where original has no accents but variants might)

    # 3. Transposition: swap first and last name
    transposed = f"{last} {first}"
    variants.add(transposed)

    # 4. Single char deletion on last name (only if last name >= 5 chars)
    if len(last) >= 5:
        for i in range(min(len(last), 4)):
            deleted = last[:i] + last[i + 1:]
            variants.add(f"{first} {deleted}")

    # 5. Common double-letter collapse (only if last name >= 5 chars)
    if len(last) >= 5:
        for double, single in [("ll", "l"), ("tt", "t"), ("nn", "n"), ("rr", "r"), ("ss", "s")]:
            if double in last:
                collapsed = last.replace(double, single, 1)
                variants.add(f"{first} {collapsed}")

    # 6. Period in initials: "CJ" -> "C.J.", "CJ" -> "C J"
    if len(first) == 2 and first.isalpha():
        variants.add(f"{first[0]}.{first[1]}. {last}")
        variants.add(f"{first[0]} {first[1]} {last}")
        variants.add(f"{first[0]}.{first[1]} {last}")

    # Remove the original normalized name
    variants.discard(normalized)

    return sorted(variants)
