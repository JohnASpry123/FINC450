"""Merge a refreshed Bloomberg export after verifying dates and overlapping quotes.

No network access or Bloomberg entitlement is supplied by this utility.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from fx_data import DEFAULT_INPUT, DataQualityError, load_exchange_rates, provenance, validate_series


def merge_observations(history_dates, history, incoming_dates, incoming):
    validate_series(history_dates, history)
    validate_series(incoming_dates, incoming)
    if set(history) != set(incoming):
        raise DataQualityError('Currency columns differ; reconcile tickers and quote conventions first.')
    if incoming_dates[-1] <= history_dates[-1]:
        raise DataQualityError('Incoming data contains no newer observations.')
    old = {d: i for i, d in enumerate(history_dates)}
    new = {d: i for i, d in enumerate(incoming_dates)}
    overlap = old.keys() & new.keys()
    if not overlap:
        raise DataQualityError('Include at least one overlapping week to verify quote conventions.')
    for date in sorted(overlap):
        for currency in history:
            left, right = history[currency][old[date]], incoming[currency][new[date]]
            equal = left is None and right is None
            if left is not None and right is not None:
                equal = math.isclose(left, right, rel_tol=1e-12, abs_tol=0)
            if not equal:
                raise DataQualityError(f'Overlapping quote changed: {date} {currency}: {left} -> {right}. '
                                       'Review revisions/scaling before replacing the full history.')
    dates = sorted(old.keys() | new.keys())
    data = {c: [history[c][old[d]] if d in old else incoming[c][new[d]] for d in dates] for c in history}
    validate_series(dates, data)  # Reject a missing week at the join too.
    return dates, data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--incoming', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', type=dt.date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    if args.output.resolve() in (args.history.resolve(), args.incoming.resolve()) or args.output.exists() or args.output.with_suffix(".provenance.json").exists():
        parser.error('Choose a new output path; source exports and existing snapshots are preserved.')
    hd, history = load_exchange_rates(args.history)
    nd, incoming = load_exchange_rates(args.incoming)
    dates, data = merge_observations(hd, history, nd, incoming)
    metadata = {'history': provenance(args.history, hd, history, as_of=args.as_of),
                'incoming': provenance(args.incoming, nd, incoming, as_of=args.as_of),
                'first_observation': dates[0].isoformat(), 'last_observation': dates[-1].isoformat(),
                'overlap_policy': 'Reject revisions or changed missingness; relative tolerance 1e-12'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(['Date', *data])
        for i, date in enumerate(dates):
            writer.writerow([date.isoformat(), *['' if data[c][i] is None else repr(data[c][i]) for c in data]])
    metadata['merged'] = provenance(args.output, dates, data, as_of=args.as_of)
    args.output.with_suffix('.provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Saved {len(dates)} weeks through {dates[-1]} to {args.output}')


if __name__ == '__main__':
    main()
