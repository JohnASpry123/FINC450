"""Data-contract, numerical and integration regression tests; no network required."""
import csv
import datetime as dt
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from bloomberg_weekly_loader import load_bloomberg_weekly_exchange_rates, write_csv
from exchange_rate_analysis import (compute_weekly_log_changes, correlation_matrices,
                                    plot_series_svg, summarize_percent_changes)
from fx_data import (DEFAULT_INPUT, ROOT, DataQualityError, load_exchange_rates,
                     parse_date, parse_float, provenance)
from refresh_exchange_rates import merge_observations

D = [dt.date(2026, 1, 2) + dt.timedelta(weeks=i) for i in range(5)]


class LoadingTests(unittest.TestCase):
    def load_fixture(self, rows, header=('Date', 'JPYUSD'), **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quotes.csv'
            with path.open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
            return load_exchange_rates(path, **kwargs)

    def test_date_formats_and_serial(self):
        self.assertEqual(parse_date('1/30/2026'), parse_date('2026-01-30'))
        self.assertEqual(parse_date('46052'), dt.date(2026, 1, 30))
        with self.assertRaises(DataQualityError): parse_date('not a date')

    def test_precision_preserved(self):
        dates, data = self.load_fixture([['1/23/2026', '.006423'], ['1/30/2026', '.006461']])
        self.assertEqual(data['JPYUSD'], [.006423, .006461])
        self.assertEqual(dates[-1], dt.date(2026, 1, 30))

    def test_rounded_constant_and_variable_quotes_rejected(self):
        for values in [('.01', '.01'), ('$1.03', '$1.01')]:
            with self.subTest(values=values), self.assertRaisesRegex(DataQualityError, 'rounding'):
                self.load_fixture([[D[0], values[0]], [D[1], values[1]]])

    def test_missing_retained_warned_and_strict_failure(self):
        rows = [[D[0], '.00642'], [D[1], '#N/A'], [D[2], '.00646']]
        with self.assertWarnsRegex(UserWarning, '1 missing quotes'):
            _, data = self.load_fixture(rows)
        self.assertIsNone(data['JPYUSD'][1])
        with self.assertRaisesRegex(DataQualityError, 'missing quotes'):
            self.load_fixture(rows, strict_missing=True)

    def test_invalid_values_do_not_silently_become_missing(self):
        for value in ['#VALUE!', 'oops', 'NaN', 'inf', '0', '-.1']:
            with self.subTest(value=value), self.assertRaises(DataQualityError): parse_float(value)

    def test_dates_duplicates_reverse_gap_and_off_cycle(self):
        for dates in [(D[0], D[0]), (D[1], D[0]), (D[0], D[2]), (D[0], D[1] + dt.timedelta(days=1))]:
            with self.subTest(dates=dates), self.assertRaises(DataQualityError):
                self.load_fixture([[dates[0], '.00642'], [dates[1], '.00646']])

    def test_bad_dates_and_row_widths_rejected(self):
        for row in [['bad-date', '.00646'], ['', '.00646'], [D[1]], [D[1], '.00646', 'extra'], []]:
            with self.subTest(row=row), self.assertRaises(DataQualityError):
                self.load_fixture([[D[0], '.00642'], row])

    def test_duplicate_header_rejected(self):
        with self.assertRaisesRegex(DataQualityError, 'unique'):
            self.load_fixture([], header=('Date', 'JPYUSD', 'JPYUSD'))

    def test_empty_and_all_missing_rejected(self):
        with self.assertRaises(DataQualityError): self.load_fixture([])
        with self.assertRaises(DataQualityError): self.load_fixture([[D[0], ''], [D[1], '#N/A']])


class CalculationTests(unittest.TestCase):
    def test_known_log_returns_and_sample_sd(self):
        data = {'EURUSD': [1, 1.1, .99]}
        changes = compute_weekly_log_changes(D[:3], data)
        values = [100 * math.log(1.1), 100 * math.log(.9)]
        self.assertIsNone(changes['EURUSD'][0][1])
        for (_, actual), expected in zip(changes['EURUSD'][1:], values):
            self.assertAlmostEqual(actual, expected)
        result = summarize_percent_changes(changes)['EURUSD']
        self.assertEqual(result['observations'], 2)
        self.assertAlmostEqual(result['average_weekly_percent_change'], statistics.mean(values))
        self.assertAlmostEqual(result['std_dev_weekly_percent_change'], statistics.stdev(values))
        restricted = summarize_percent_changes(changes, D[1], D[2])
        self.assertEqual(restricted['EURUSD'], result)

    def test_insufficient_returns_keep_counts_and_undefined_sd(self):
        result = summarize_percent_changes({'EURUSD': [(D[0], None), (D[1], 2.0)],
                                            'JPYUSD': [(D[0], None)]})
        self.assertEqual(result['EURUSD']['observations'], 1)
        self.assertEqual(result['EURUSD']['average_weekly_percent_change'], 2)
        self.assertIsNone(result['EURUSD']['std_dev_weekly_percent_change'])
        self.assertEqual(result['JPYUSD']['observations'], 0)
        self.assertIsNone(result['JPYUSD']['average_weekly_percent_change'])

    def test_no_return_bridges_missing_quote(self):
        result = compute_weekly_log_changes(D, {'JPYUSD': [.0064, None, .0065, .0066, .0067]})['JPYUSD']
        self.assertEqual([v for _, v in result[:3]], [None, None, None])
        self.assertAlmostEqual(result[3][1], 100 * math.log(.0066 / .0065))

    def test_date_and_length_validation_in_calculation(self):
        for dates, values in [(D[:3], [1, 2]), ([D[0], D[2]], [1, 2])]:
            with self.assertRaises(DataQualityError): compute_weekly_log_changes(dates, {'EURUSD': values})

    def test_correlations_pair_by_date_and_count(self):
        changes = {'EURUSD': [(D[0], 1), (D[1], 2), (D[2], 3)],
                   'GBPUSD': [(D[2], 6), (D[0], 2), (D[1], 4)],
                   'JPYUSD': [(D[0], 0), (D[1], 0), (D[2], 0)],
                   'CNYUSD': [(D[1], 8), (D[2], None)]}
        corr, n = correlation_matrices(changes)
        self.assertAlmostEqual(corr['EURUSD']['GBPUSD'], 1)
        self.assertEqual(n['EURUSD']['GBPUSD'], 3)
        self.assertIsNone(corr['EURUSD']['JPYUSD'])
        self.assertEqual(n['EURUSD']['CNYUSD'], 1)
        self.assertIsNone(corr['EURUSD']['CNYUSD'])
        changes['GBPUSD'].append((D[0], 5))
        with self.assertRaises(DataQualityError): correlation_matrices(changes)

    def test_svg_breaks_missing_quotes_and_shows_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plot.svg'
            plot_series_svg(D, [.0064, .0065, None, .0066, .0067], 'JPYUSD', path)
            svg = path.read_text()
            self.assertEqual(svg.count('<polyline'), 2)
            self.assertIn('2026-01-30', svg)
            self.assertIn('source scale', svg)


class RefreshTests(unittest.TestCase):
    def test_append_preserves_quotes_and_history(self):
        dates, data = merge_observations(D[:3], {'EURUSD': [1.1234, 1.1235, 1.1236]},
                                        D[2:], {'EURUSD': [1.1236, 1.1237, 1.1238]})
        self.assertEqual(dates, D)
        self.assertEqual(data['EURUSD'], [1.1234, 1.1235, 1.1236, 1.1237, 1.1238])

    def test_reject_stale_overlap_revision_schema_and_no_overlap(self):
        old = {'EURUSD': [1.1234, 1.1235, 1.1236]}
        cases = [(D[:3], old), (D[2:], {'EURUSD': [1.1237, 1.1238, 1.1239]}),
                 (D[2:], {'GBPUSD': [1.1236, 1.1237, 1.1238]}),
                 (D[3:], {'EURUSD': [1.1237, 1.1238]})]
        for dates, values in cases:
            with self.subTest(dates=dates, values=values), self.assertRaises(DataQualityError):
                merge_observations(D[:3], old, dates, values)

    def test_refresh_cli_writes_verifiable_snapshot_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for filename, dates, values in [('history.csv', D[:3], [1.1234, 1.1235, 1.1236]),
                                             ('incoming.csv', D[2:], [1.1236, 1.1237, 1.1238])]:
                with (base / filename).open('w', newline='') as handle:
                    writer = csv.writer(handle); writer.writerow(['Date', 'EURUSD'])
                    writer.writerows(zip(dates, values))
            output = base / 'merged.csv'
            command = [sys.executable, str(ROOT / 'refresh_exchange_rates.py'),
                       '--history', str(base / 'history.csv'), '--incoming', str(base / 'incoming.csv'),
                       '--output', str(output), '--as-of', '2026-01-30']
            run = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            dates, data = load_exchange_rates(output)
            self.assertEqual(dates, D); self.assertEqual(data['EURUSD'][-1], 1.1238)
            meta = json.loads(output.with_suffix('.provenance.json').read_text())
            self.assertFalse(meta['merged']['stale'])
            self.assertEqual(meta['last_observation'], '2026-01-30')
            run = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0)

    def test_future_and_stale_metadata(self):
        data = {'EURUSD': [1.1234] * 5}
        meta = provenance(DEFAULT_INPUT, D, data, as_of=dt.date(2026, 10, 15))
        self.assertTrue(meta['stale']); self.assertEqual(meta['age_days'], 258)
        with self.assertRaises(DataQualityError): provenance(DEFAULT_INPUT, D, data, as_of=D[0])


class RepositoryRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            cls.dates, cls.data = load_exchange_rates()

    def test_repository_cutoff_counts_missing_and_precision(self):
        self.assertEqual(len(self.dates), 1361)
        self.assertEqual(self.dates[0], dt.date(2000, 1, 7))
        self.assertEqual(self.dates[-1], dt.date(2026, 1, 30))
        self.assertEqual(self.data['JPYUSD'][-1], .006461)
        self.assertEqual(sum(v is None for values in self.data.values() for v in values), 6)
        changes = compute_weekly_log_changes(self.dates, self.data)
        stats = summarize_percent_changes(changes)
        self.assertAlmostEqual(stats['JPYUSD']['std_dev_weekly_percent_change'], 1.347691, places=6)
        self.assertEqual(stats['CNYUSD']['observations'], 1350)
        self.assertEqual(stats['IDRUSD']['observations'], 1358)
        self.assertEqual(stats['EURUSD']['observations'], 1360)

    def test_precise_csv_agrees_with_workbook(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            dates, data = load_exchange_rates(ROOT / 'Bloomberg Weekly Exchange Rates since 2000 1 31 2026.csv')
        self.assertEqual(dates, self.dates)
        for c, values in data.items():
            for a, b in zip(values, self.data[c]):
                if a is None or b is None: self.assertIs(a, b)
                else: self.assertTrue(math.isclose(a, b, rel_tol=1e-15, abs_tol=0))

    def test_old_file_rejected(self):
        with self.assertRaisesRegex(DataQualityError, 'rounding'):
            load_exchange_rates(ROOT / 'Bloomberg Weekly Exchange Rates since 2000 1 28 2026.cvs.csv')

    def test_xlsx_export_round_trip(self):
        sheet = load_bloomberg_weekly_exchange_rates(str(DEFAULT_INPUT))
        self.assertEqual(sheet.rows[-1][0], '2026-01-30')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'quotes.csv'
            write_csv(sheet, str(path))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore'); dates, data = load_exchange_rates(path)
            self.assertEqual(dates, self.dates); self.assertEqual(data, self.data)

    def test_1904_dates_and_uncached_formulas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.xlsx'
            for uncached in (False, True):
                with zipfile.ZipFile(DEFAULT_INPUT) as source, zipfile.ZipFile(path, 'w') as target:
                    for item in source.infolist():
                        raw = source.read(item.filename)
                        if item.filename == 'xl/workbook.xml':
                            text = raw.decode(); text = text.replace('date1904="false"', 'date1904="true"').replace('date1904="0"', 'date1904="1"')
                            if 'date1904=' not in text: text = text.replace('<workbookPr ', '<workbookPr date1904="1" ', 1)
                            raw = text.encode()
                        if uncached and item.filename == 'xl/worksheets/sheet1.xml':
                            text = raw.decode().replace('<v>36532</v>', '<f>1+1</f>', 1); raw = text.encode()
                        target.writestr(item, raw)
                if uncached:
                    with self.assertRaisesRegex(ValueError, 'cached'): load_bloomberg_weekly_exchange_rates(str(path))
                else:
                    sheet = load_bloomberg_weekly_exchange_rates(str(path))
                    self.assertEqual(sheet.rows[0][0], (dt.date(1904, 1, 1) + dt.timedelta(days=36532)).isoformat())

    def test_cli_end_to_end_and_staleness_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results'
            command = [sys.executable, str(ROOT / 'exchange_rate_analysis.py'), '--as-of', '2026-10-15', '--output-dir', str(output)]
            run = subprocess.run(command, cwd=directory, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('HISTORICAL DATA', run.stdout)
            meta = json.loads((output / 'analysis_manifest.json').read_text())
            self.assertEqual(meta['last_observation'], '2026-01-30')
            self.assertEqual(len(list((output / 'plots').glob('*.svg'))), 18)
            failed_output = Path(directory) / 'must_not_exist'
            run = subprocess.run(command + ['--require-current', '--output-dir', str(failed_output)], text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0); self.assertFalse(failed_output.exists())


if __name__ == '__main__':
    unittest.main()
