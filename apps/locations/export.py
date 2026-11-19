"""Рендеринг експорту локацій у CSV/JSON через pandas."""

from dataclasses import dataclass

import pandas as pd
from django.utils import timezone

EXPORT_COLUMNS = (
    "id",
    "name",
    "description",
    "address",
    "latitude",
    "longitude",
    "category_id",
    "category_name",
    "author_id",
    "author_username",
    "avg_rating",
    "reviews_count",
    "views_7d",
    "popularity",
    "created_at",
)


# Комірки, які Excel/LibreOffice виконують як формулу (CSV injection).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _neutralize_formula(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


class ExportFormat:
    CSV = "csv"
    JSON = "json"
    CHOICES = (CSV, JSON)


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    content_type: str
    filename: str


def render_export(rows: list[dict], file_format: str) -> ExportFile:
    frame = pd.DataFrame.from_records(rows, columns=EXPORT_COLUMNS)
    filename = f"locations-{timezone.localdate():%Y-%m-%d}.{file_format}"
    if file_format == ExportFormat.JSON:
        content = frame.to_json(orient="records", force_ascii=False).encode()
        return ExportFile(content, "application/json", filename)
    # Назву, опис, адресу вводять користувачі: без префікса «'» рядок на кшталт
    # =HYPERLINK(...) виконався б у табличному редакторі того, хто відкрив експорт.
    # "str" — рядковий dtype pandas 3.
    text_columns = frame.select_dtypes(include=["object", "str"]).columns
    frame[text_columns] = frame[text_columns].map(_neutralize_formula)
    # BOM, щоб Excel розпізнав UTF-8 і коректно показав кирилицю.
    content = frame.to_csv(index=False).encode("utf-8-sig")
    return ExportFile(content, "text/csv; charset=utf-8", filename)
