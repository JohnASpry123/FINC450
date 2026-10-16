"""Reproduce a common-date comparison of the legacy rounded export and stored quotes."""
from __future__ import annotations
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exchange_rate_analysis import compute_weekly_log_changes, correlation_matrices, write_matrix_csv
from fx_data import DEFAULT_INPUT, ROOT, load_exchange_rates, provenance


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    legacy_path = ROOT / 'Bloomberg Weekly Exchange Rates since 2000 1 28 2026.cvs.csv'
    old_dates, old = load_exchange_rates(legacy_path, allow_rounded=True)
    new_dates, new = load_exchange_rates(DEFAULT_INPUT)
    common = sorted(set(old_dates) & set(new_dates))
    if common != old_dates or new_dates[:len(common)] != common:
        raise ValueError('Expected identical weekly history with the precise source extending it.')
    full_new = new
    new = {c: v[:len(common)] for c, v in new.items()}
    old_returns = compute_weekly_log_changes(common, old)
    new_returns = compute_weekly_log_changes(common, new)
    out = ROOT / 'outputs' / 'precision_audit'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for currency in old:
        # Identical return dates, including matching treatment of missing quotes.
        pairs = [(a, b) for (_, a), (_, b) in zip(old_returns[currency], new_returns[currency])
                 if a is not None and b is not None]
        a, b = [p[0] for p in pairs], [p[1] for p in pairs]
        rows.append({'Currency': currency, 'Paired returns': len(a),
                     'Rounded mean (%)': statistics.fmean(a), 'Precise mean (%)': statistics.fmean(b),
                     'Rounded SD (%)': statistics.stdev(a), 'Precise SD (%)': statistics.stdev(b),
                     'SD ratio rounded/precise': statistics.stdev(a) / statistics.stdev(b),
                     'Rounded zero returns (%)': 100 * a.count(0) / len(a),
                     'Precise zero returns (%)': 100 * b.count(0) / len(b)})
    with (out / 'common_sample_statistics.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    oc, on = correlation_matrices(old_returns)
    nc, nn = correlation_matrices(new_returns)
    write_matrix_csv(oc, out / 'rounded_correlations.csv')
    write_matrix_csv(nc, out / 'precise_correlations.csv')
    write_matrix_csv(on, out / 'rounded_correlation_counts.csv')
    write_matrix_csv(nn, out / 'precise_correlation_counts.csv')
    delta = {c: {d: None if oc[c][d] is None or nc[c][d] is None else nc[c][d] - oc[c][d]
                 for d in old} for c in old}
    write_matrix_csv(delta, out / 'correlation_delta_precise_minus_rounded.csv')
    currencies = list(old)
    diffs = sorted([(abs(delta[c][d]), c, d, oc[c][d], nc[c][d])
                    for i, c in enumerate(currencies) for d in currencies[i + 1:]
                    if delta[c][d] is not None], reverse=True)
    lost = [(c, d) for i, c in enumerate(currencies) for d in currencies[i + 1:]
            if oc[c][d] is None and nc[c][d] is not None]
    mismatched_missing = sum((a is None) != (b is None) for c in old for a, b in zip(old[c], new[c]))
    beyond_rounding = sum(abs(a - b) > .005000000001 for c in old for a, b in zip(old[c], new[c])
                          if a is not None and b is not None)
    double_round_mismatches = sum(
        abs(float(Decimal(str(b)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
                  .quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) - a) > 1e-10
        for c in old for a, b in zip(old[c], new[c]) if a is not None and b is not None)
    lines = ['# Exchange-rate precision audit', '',
             f'Common price dates: **{common[0]} through {common[-1]}** ({len(common):,} weeks). '
             'Both versions use 100 × Δln(S), sample SD, and the same valid paired return dates. '
             'The January 30 observation is excluded here to isolate precision effects.', '',
             f'Overlap checks: {mismatched_missing} differences in missingness; {beyond_rounding} quote differences '
             'exceed the single-step half-cent rounding bound. However, rounding precise quotes first to four '
             f'decimals and then to two (decimal half-up) reproduces the legacy values with {double_round_mismatches} '
             'mismatches. This is evidence of double rounding; the original export procedure is unknown.', '',
             '| Currency | Paired returns | Rounded mean % | Precise mean % | Rounded SD % | Precise SD % | SD ratio | Rounded zero returns % | Precise zero returns % |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        vals = list(row.values())
        lines.append('| ' + ' | '.join([vals[0], str(vals[1]), *[f'{v:.4f}' for v in vals[2:]]]) + ' |')
    lines += ['', '## Correlations', '',
              f'Rounding makes {len(lost)} of 153 distinct currency-pair correlations undefined '
              'that are defined in the precise data. JPYUSD and SARUSD become constant series; '
              'undefined correlations are blank, never zero.', '',
              '| Pair | Rounded correlation | Precise correlation | Absolute change |',
              '|---|---:|---:|---:|']
    lines += [f'| {c} / {d} | {a:.4f} | {b:.4f} | {diff:.4f} |' for diff, c, d, a, b in diffs[:10]]
    lines += ['', '## Interpretation and limits', '',
              'Rounding suppresses many ordinary weekly moves and concentrates changes into artificial jumps. '
              'It can either inflate volatility or erase it. Mean log returns also change because endpoints '
              'are rounded; with missing quotes, the mean averages only valid adjacent weekly intervals.', '',
              'The main corrected outputs include January 30, 2026 and therefore have one additional week. '
              'They remain historical: no Fall 2026 observations were obtained. Six source quotes are missing '
              '(five CNYUSD and one IDRUSD); each removes two adjacent weekly returns. '
              'Pairwise correlation sample sizes are exported separately.', '',
              'The workbook preserves stored quote values; the precise CSV agrees within 1e-15 relative tolerance '
              '(one binary floating-point last-bit difference). Extra workbook digits often reflect Excel binary '
              'serialization, not extra economic precision. No missing quote is filled and no currency scale '
              'is changed. Constant quote scaling cancels in log returns; changing scaling would not.', '',
              'Some source series appear scaled (notably IDRUSD, KRWUSD and LKRUSD). The original export does '
              'not include ticker scale metadata. Charts label the source scale, and a future Bloomberg refresh '
              'must verify the same tickers, field, quote direction, units and weekly convention.', '',
              'Reproduce with `python analysis/compare_precision.py`. Numeric CSVs and the volatility chart '
              'are in this directory.', '', '![Volatility comparison](volatility_comparison.png)', '']
    (out / 'REPORT.md').write_text('\n'.join(lines))
    import datetime as dt
    metadata = {'rounded': provenance(legacy_path, old_dates, old, as_of=dt.date(2026, 10, 15)),
                'precise': provenance(DEFAULT_INPUT, new_dates, full_new,
                                      as_of=dt.date(2026, 10, 15)),
                'comparison_start': common[0].isoformat(), 'comparison_end': common[-1].isoformat()}
    (out / 'sources.json').write_text(json.dumps(metadata, indent=2) + '\n')
    fig, ax = plt.subplots(figsize=(12, 9))
    y = list(range(len(rows)))
    ax.barh([i - .19 for i in y], [r['Rounded SD (%)'] for r in rows], height=.38, label='Rounded export', color='#bd6c32')
    ax.barh([i + .19 for i in y], [r['Precise SD (%)'] for r in rows], height=.38, label='Stored full-precision quotes', color='#2f5597')
    ax.set_yticks(y, currencies); ax.invert_yaxis()
    ax.set_xlabel('Sample standard deviation of weekly log returns (%)', fontsize=13)
    ax.set_title(f'Rounding materially changes measured currency volatility\nSame dates: {common[0]} to {common[-1]}', fontsize=16)
    ax.tick_params(labelsize=12); ax.legend(loc='lower right', fontsize=12)
    ax.spines[['top', 'right']].set_visible(False)
    fig.tight_layout(); fig.savefig(out / 'volatility_comparison.png', dpi=160); plt.close(fig)
    print('\n'.join(lines[:12])); print(f'Full report: {out / "REPORT.md"}')


if __name__ == '__main__':
    main()
