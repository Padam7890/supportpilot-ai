"""Provider-neutral catalog candidate and category primitives."""

import re
from dataclasses import dataclass

from app.models import CatalogProduct, CatalogVariant

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "best",
        "cheap",
        "good",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "please",
        "recommend",
        "product",
        "recommendation",
        "under",
        "with",
        "for",
        "the",
        "to",
        "want",
        "looking",
        "find",
        "show",
        "suggest",
    }
)

CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "phone": (
        "phone",
        "phones",
        "smartphone",
        "smartphones",
        "smart phone",
        "smart phones",
        "mobile",
        "mobiles",
        "mobile phone",
        "mobile phones",
        "cell phone",
        "cellphone",
        "cell phones",
        "मोबाइल",
        "मोबाइल फोन",
        "फोन",
    ),
    "laptop": (
        "laptop",
        "laptops",
        "notebook",
        "notebooks",
        "computer",
        "computers",
        "ल्यापटप",
        "कम्प्युटर",
    ),
    "earbuds": (
        "earbud",
        "earbuds",
        "wireless earphone",
        "wireless earphones",
        "tws",
        "earphone",
        "earphones",
        "इयरबड",
        "इयरफोन",
        "headphone",
        "headphones",
    ),
    "tv": ("tv", "television", "televisions", "टिभी"),
    "fridge": ("fridge", "refrigerator", "refrigerators", "रेफ्रिजरेटर"),
}


@dataclass(frozen=True)
class CatalogCandidate:
    product: CatalogProduct
    variant: CatalogVariant

    @property
    def searchable_text(self) -> str:
        attrs = " ".join(f"{key} {value}" for key, value in self.variant.attributes.items())
        specs = " ".join(f"{key} {value}" for key, value in self.product.specifications.items())
        return " ".join(
            value or ""
            for value in (
                self.product.title,
                self.product.description,
                self.product.brand,
                self.product.category,
                self.variant.title,
                attrs,
                specs,
            )
        ).casefold()


def _terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        term
        for term in re.findall(r"[\w]+", value.casefold())
        if len(term) > 2 and term not in STOPWORDS
    ]


def normalize_category(value: str | None) -> str | None:
    if not value:
        return value
    folded = " ".join(value.casefold().split())
    for canonical, aliases in CATEGORY_SYNONYMS.items():
        if folded == canonical or folded in aliases:
            return canonical
    return value.strip()


def category_aliases(value: str | None) -> tuple[str, ...]:
    canonical = normalize_category(value)
    return CATEGORY_SYNONYMS.get(canonical or "", (value,) if value else ())


def candidate_matches_category(candidate: CatalogCandidate, category: str | None) -> bool:
    if not category:
        return True
    searchable = candidate.searchable_text
    aliases = category_aliases(category)
    if aliases:
        return any(alias.casefold() in searchable for alias in aliases)
    return category.casefold() in searchable
