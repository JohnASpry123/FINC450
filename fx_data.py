"""Shared, validated Bloomberg input for statistics and charts (standard library)."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import math
from pathlib import Path
import re
import warnings

from bloomberg_weekly_loader import load_bloomberg_weekly_exchange_rates

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / 'Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx'
MISSING = {'', '#N/A', '#N/A N/A', 'N/A', 'NA'}


class DataQualityError(ValueError):
    """The input cannot safely be interpreted as weekly exchange rates."""


def parse_date(value: str) -> dt.date:
    value = value.strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Compatibility with the original raw XLSX-to-CSV export (1900 date system).
    if re.fullmatch(r'\d+(?:\.0+)?', value):
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(float(value)))
    raise DataQualityError(f'Invalid date: {value!r}')


def parse_float(value: str) -> float | None:
    cleaned = value.strip().replace('$', '').replace(',', '').strip()
    if cleaned.upper() in MISSING:
        return None
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise DataQualityError(f'Invalid quote: {value!r}') from exc
    if not math.isfinite(number) or number <= 0:
        raise DataQualityError(f'Quote must be finite and positive: {value!r}')
    return number


def validate_dates(dates):
    if len(dates) < 2:
        raise DataQualityError('At least two dated observations are required.')
    for previous, current in zip(dates, dates[1:]):
        days = (current - previous).days
        if days != 7:
            raise DataQualityError(
                f'Dates must be unique, increasing and exactly seven days apart: '
                f'{previous} -> {current} ({days} days). Do not bridge missing weeks.'
            )


def validate_series(dates, data):
    validate_dates(dates)
    for currency, values in data.items():
        if len(values) != len(dates):
            raise DataQualityError(f'{currency}: quote/date lengths differ.')
        if any(v is not None and (not math.isfinite(v) or v <= 0) for v in values):
            raise DataQualityError(f'{currency}: quotes must be finite and positive.')


def load_exchange_rates(path=DEFAULT_INPUT, *, allow_rounded=False, strict_missing=False):
    """Read CSV or cached XLSX values; never impute, sort, or discard bad rows.

    allow_rounded is only for the historical comparison, not the analysis CLI.
    Recognized missing quotes are retained and reported; malformed values fail.
    """
    path = Path(path)
    if path.suffix.lower() == '.xlsx':
        sheet = load_bloomberg_weekly_exchange_rates(str(path))
        header, rows = sheet.header, sheet.rows
    else:
        with path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.reader(handle)
            header, rows = next(reader, []), list(reader)
    if not header or header[0] != 'Date' or len(header) < 2:
        raise DataQualityError('Expected Date followed by currency columns.')
    if len(set(header)) != len(header) or any(not re.fullmatch(r'[A-Z]{3}USD', c) for c in header[1:]):
        raise DataQualityError('Currency headers must be unique XXXUSD identifiers.')
    dates, data = [], {c: [] for c in header[1:]}
    missing = []
    for line, row in enumerate(rows, 2):
        # The older export contains this one Bloomberg metadata row.
        if row and row[0] == '(auto)' and all(not x.strip() for x in row[1:]):
            continue
        if len(row) != len(header):
            raise DataQualityError(f'Row {line}: expected {len(header)} fields, got {len(row)}.')
        date = parse_date(row[0])
        dates.append(date)
        for currency, raw in zip(header[1:], row[1:]):
            try:
                value = parse_float(raw)
            except DataQualityError as exc:
                raise DataQualityError(f'Row {line}, {currency}: {exc}') from exc
            data[currency].append(value)
            if value is None:
                missing.append(f'{date} {currency}')
    validate_series(dates, data)
    rounded = []
    for currency, values in data.items():
        valid = [v for v in values if v is not None]
        if not valid:
            raise DataQualityError(f'{currency}: no observed quotes.')
        # Detect display-formatted cents, including constant 0.01 JPY quotes.
        cent_fraction = sum(abs(v * 100 - round(v * 100)) < 1e-8 for v in valid) / len(valid)
        if cent_fraction >= .98:
            rounded.append(currency)
    if rounded and not allow_rounded:
        raise DataQualityError('Suspected two-decimal rounding (>=98% cent-quantized quotes): '
                               + ', '.join(rounded) + '. Use the stored XLSX values or precise CSV.')
    if missing:
        message = f'{len(missing)} missing quotes retained (no fill): ' + ', '.join(missing)
        if strict_missing:
            raise DataQualityError(message)
        warnings.warn(message, UserWarning, stacklevel=2)
    return dates, data


def provenance(path, dates, data, *, as_of=None, max_age_days=14):
    as_of = as_of or dt.datetime.now(dt.timezone.utc).date()
    if dates[-1] > as_of:
        raise DataQualityError(f'Last observation {dates[-1]} is after as-of date {as_of}.')
    if max_age_days < 0:
        raise DataQualityError('max_age_days must be nonnegative.')
    age = (as_of - dates[-1]).days
    missing = {c: [d.isoformat() for d, v in zip(dates, values) if v is None]
               for c, values in data.items()}
    return {
        'source_file': Path(path).name,
        'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'first_observation': dates[0].isoformat(), 'last_observation': dates[-1].isoformat(),
        'rows': len(dates), 'currencies': len(data), 'as_of': as_of.isoformat(),
        'age_days': age, 'max_age_days': max_age_days, 'stale': age > max_age_days,
        'method': '100 * (ln(S_t) - ln(S_t-1)); sample SD (ddof=1); pairwise Pearson correlation',
        'quote_units': 'USD quotes in source scale; currency-specific scale factors unverified',
        'missing_quotes': missing,
        'precision_check': 'Reject columns with >=98% cent-quantized quotes; heuristic, not proof of precision',
    }
