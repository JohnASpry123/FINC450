# FINC450 — weekly exchange-rate analysis

**Data cutoff: January 30, 2026. This is a historical dataset, not current Fall 2026 data.**
The repository has 1,361 weekly price rows (January 7, 2000–January 30, 2026),
18 currencies, and six explicitly missing quotes. A fresh download is required to
extend the sample. Running the analysis does not download new observations.

## Corrected source and material impact

The analysis and charts default to the **stored numeric values** in
`Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx`. The accompanying
`Bloomberg Weekly Exchange Rates since 2000 1 31 2026.csv` is also supported and
agrees to floating-point precision. Workbook serialization has one last-bit
float difference; extra serialization digits do not imply greater economic accuracy.

The former default, `Bloomberg Weekly Exchange Rates since 2000 1 28 2026.cvs.csv`,
ends January 23 and contains currency-formatted values rounded to two decimals.
It is retained solely as audit evidence and is rejected by normal analysis.
On the **same dates**, weekly log-return sample standard deviations change as follows:

| Currency | Rounded input | Precise input |
|---|---:|---:|
| JPY | 0.0000% | 1.3481% |
| INR | 8.4889% | 0.8225% |
| RUB | 9.1464% | 2.3332% |
| CNY | 1.1965% | 0.3788% |

Rounding makes 33 of 153 distinct currency-pair correlations undefined. For
example, the ZAR/KRW correlation is 0.0641 with rounded quotes versus 0.4680 with
precise quotes. All overlapping legacy quotes can be reproduced by decimal
half-up rounding first to four decimals, then to two. This supports a double-rounding
explanation; the original export procedure is unknown.

See the [full precision audit](outputs/precision_audit/REPORT.md) for all currencies,
means, volatility, zero-return frequencies, correlation changes and a comparison
chart. Its common sample ends January 23; corrected main outputs include January 30.
Obsolete `weekly_percent_changes.csv` and `weekly_percent_change_stats.csv` were
removed to avoid distributing rounded-data results alongside the corrected analysis;
previous versions remain in Git history.

## Reproduce the analysis

Use **Python 3.11 or newer**. Core loading, analysis, SVG charts and tests use only
the standard library. From the repository root:

```bash
python -m unittest discover -s tests -v
python bloomberg_weekly_loader.py \
  --xlsx "Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx" \
  --output outputs/bloomberg_weekly_exchange_rates.csv
python exchange_rate_analysis.py --as-of 2026-10-15
```

`--as-of` records the assessment date, **not** the sample endpoint. Omitting it
uses today's UTC date. The checked-in analysis uses the October 15 inspection date.
Inputs more than 14 days old produce a historical-data notice. Use
`--require-current` to fail rather than write outputs for stale data; change the
threshold with `--max-age-days`. Future-dated observations are rejected.

To use an explicit precise CSV or a different output folder:

```bash
python exchange_rate_analysis.py \
  --input "Bloomberg Weekly Exchange Rates since 2000 1 31 2026.csv" \
  --output-dir outputs/csv_check --as-of 2026-10-15
```

All default paths are relative to the script's repository directory, not the
working directory. Explicit relative paths are resolved from the working directory.
The XLSX exporter reads the first worksheet via workbook relationships, respects
the 1900/1904 Excel date system, exports ISO dates, and preserves numeric quote text.
It reads **cached values only**: it cannot recalculate Bloomberg formulas. Uncached
formulas fail. Refresh and save the workbook in Excel before extraction.

### PNG figures and the precision comparison

Install the optional plotting dependency in an isolated environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-plots.txt
python analysis/plot_exchange_rates_fred_style.py
python analysis/compare_precision.py
```

On Windows, activate with `.venv\Scripts\activate` instead. The PNG chart script
accepts `--input` and `--output-dir`, using the same validated loader as statistics.
The comparison intentionally fixes the two historical source files and the October
15, 2026 assessment date; it is an audit of this correction, not a live report.

## Methodology and data-quality rules

- **Returns remain log returns:** `r_t = 100 * (ln(S_t) - ln(S_(t-1)))`, expressed
  in percent per week. They are neither simple returns nor annualized returns.
  For a simple return use `100 * (exp(r_t / 100) - 1)`.
- The mean is the arithmetic average of observed weekly log returns. Volatility
  is the sample standard deviation (`ddof=1`), without annualization.
- The first price row has no return. A missing quote invalidates that week's
  return and the following week's return. There is **no forward fill**, interpolation,
  or return bridging across a gap. The six source gaps are five CNYUSD quotes and
  one IDRUSD quote, leaving 1,350 and 1,358 valid returns respectively; other series
  have 1,360 valid returns. Missing quotes warn and are listed by date in metadata;
  `--strict-missing` makes any missing quote fatal.
- Dates must be valid, unique, increasing and exactly seven days apart. Missing
  weeks, duplicate dates, reversed rows, irregular intervals, malformed quotes,
  nonfinite/nonpositive quotes, duplicate headers and inconsistent row lengths fail.
  The old export's known `(auto)` metadata row is the only skipped row.
- A column with at least 98% of quotes on a two-decimal grid fails the precision
  check. This is a **heuristic** aimed at the observed defect: it cannot prove
  adequate precision or detect every mixed/coarsened export. A legitimate cent-grid
  series requires source review; normal analysis offers no silent bypass.
- Correlations use pairwise-complete **matching dates**, and sample counts are
  exported. Constant series and pairs with fewer than two observations produce
  blank/undefined correlations, never zero. Pairwise samples can differ, so a
  correlation matrix with missing observations need not be positive semidefinite.
- The 2008–2009 summary selects returns by their ending date. The preceding price
  is retained to calculate the first eligible weekly return.
- Source `XXXUSD` labels are preserved. Some quotes appear scaled (particularly
  IDRUSD, KRWUSD and LKRUSD), and the export lacks authoritative scale metadata.
  Charts say **USD quote (source scale)**. No unverified unit conversion is applied.
  A fixed multiplicative scale cancels in log returns; a scale change does not.
- Charts show actual first/last observation dates and break lines at missing quotes.
  The generated CSV returns retain floating-point precision; formatted summary
  statistics are presentation outputs and are never fed back into calculations.

### Generated files

| Location | Contents |
|---|---|
| `outputs/weekly_log_changes.csv` | Weekly log returns in percent, blanks for unavailable returns |
| `outputs/weekly_log_change_stats_full.csv` | Counts, mean and sample SD for the full historical sample |
| `outputs/weekly_log_change_stats_2008_2009.csv` | The same statistics for returns ending in 2008–2009 |
| `outputs/weekly_log_change_correlation.csv` | Pairwise Pearson correlations |
| `outputs/weekly_log_change_correlation_counts.csv` | Pairwise observation counts |
| `outputs/analysis_manifest.json` | Source filename/SHA-256, actual dates, missingness, method and freshness assessment |
| `outputs/bloomberg_weekly_exchange_rates.csv` | Exact stored workbook quote text with normalized ISO dates |
| `outputs/plots/` and `figures/` | SVG and optional PNG historical exchange-rate charts |
| `outputs/precision_audit/` | Same-date rounded/precise comparisons, source hashes and explanatory report |

## Incorporate newer observations

No new Bloomberg observations were available during this correction. The code
supports a fresh export; it does **not** claim that the January dataset is current.

1. At an entitled Bloomberg Terminal/Excel installation, refresh the original
   weekly historical request through the **last completed weekly observation**.
   Verify the same 18 tickers, historical field, quote direction, scale factors,
   weekly calendar and holiday settings. Save these details with the export.
   The repository alone does not establish the original request parameters.
2. Save a new dated XLSX with refreshed cached numeric values. Keep the first
   worksheet in the existing `Date,EURUSD,...,LKRUSD` layout. Preserve missing
   observations and full stored precision; never export currency-formatted display
   text or use Excel's “precision as displayed” setting.
3. Either analyze a fully refreshed history with `--input`, or merge an incremental
   export containing **at least one overlapping week**. The merge checks every
   overlapping value and missing marker, identical currency coverage, and weekly
   continuity. It rejects changed values/scaling, missing weeks, or an export with
   no newer observations. It writes a new file plus provenance and never overwrites
   the input history. Example placeholders, **not files currently in this repo**:

   ```bash
   python refresh_exchange_rates.py \
     --incoming data/bloomberg_refresh_YYYY-MM-DD.xlsx \
     --output data/bloomberg_weekly_through_YYYY-MM-DD.csv
   python exchange_rate_analysis.py \
     --input data/bloomberg_weekly_through_YYYY-MM-DD.csv \
     --output-dir outputs/refreshed --require-current
   python analysis/plot_exchange_rates_fred_style.py \
     --input data/bloomberg_weekly_through_YYYY-MM-DD.csv \
     --output-dir figures/refreshed
   ```

4. If Bloomberg revised historical observations, review the discrepancy and retain
   both source snapshots. After verifying units and revisions, use the fully
   refreshed export explicitly; do not bypass the merge check blindly. The
   numerical overlap tolerance is relative `1e-12`, not a license to round quotes.
5. Check the new manifest's **last observation**, missing-date warnings, and source
   hash before treating the output as current. Commit the reviewed snapshot,
   parameter notes and regenerated outputs, and update the documented cutoff and
   relevant regression expectations when changing the default source.

### Separate FRED exploratory script

The existing script is named **`exchange rate.py`**, not `exchange_rates.py`:

```bash
python -m pip install pandas numpy matplotlib fredapi openpyxl
export FRED_API_KEY=your_api_key_here
python "exchange rate.py"
```

It downloads daily FRED series for EUR, CAD, JPY and GBP and creates
`exchange_rates.xlsx`. It is a separate exploratory workflow, not a drop-in refresh
of this 18-currency Bloomberg panel. Its legacy quote-direction labels should be
verified against the FRED series metadata before teaching use. Do not splice FRED
and Bloomberg observations without reconciling direction, scale, fixing time,
coverage and weekly aggregation/holiday treatment. This correction does not add
such a mixed-source panel or claim access to a live Bloomberg feed.
