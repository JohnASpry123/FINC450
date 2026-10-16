import argparse
import csv
import json
from html import escape
import datetime as dt
import math
import pathlib
import statistics
from typing import Dict, List, Optional, Tuple


from fx_data import (DEFAULT_INPUT, ROOT, DataQualityError, load_exchange_rates,
                     parse_float, provenance, validate_series)

DATA_FILE = DEFAULT_INPUT
OUTPUT_DIR = ROOT / "outputs"
PLOTS_DIR = OUTPUT_DIR / "plots"


def compute_weekly_log_changes(
    dates: List[dt.date],
    data: Dict[str, List[Optional[float]]],
) -> Dict[str, List[Tuple[dt.date, Optional[float]]]]:
    validate_series(dates, data)
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]] = {}
    for currency, values in data.items():
        series: List[Tuple[dt.date, Optional[float]]] = []
        previous: Optional[float] = None
        for date_value, current in zip(dates, values):
            if current is None or previous is None:
                series.append((date_value, None))
                previous = current
                continue
            change = (math.log(current) - math.log(previous)) * 100
            series.append((date_value, change))
            previous = current
        percent_changes[currency] = series
    return percent_changes


def summarize_percent_changes(
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]],
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    for currency, series in percent_changes.items():
        values = [
            value
            for date_value, value in series
            if value is not None
            and (start_date is None or date_value >= start_date)
            and (end_date is None or date_value <= end_date)
        ]
        summary[currency] = {
            "observations": len(values),
            "average_weekly_percent_change": statistics.fmean(values) if values else None,
            "std_dev_weekly_percent_change": statistics.stdev(values) if len(values) > 1 else None,
        }
    return summary


def write_percent_changes_csv(
    dates: List[dt.date],
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]],
    output_path: pathlib.Path,
) -> None:
    currencies = list(percent_changes.keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Date", *currencies])
        for idx, date_value in enumerate(dates):
            row = [date_value.isoformat()]
            for currency in currencies:
                value = percent_changes[currency][idx][1]
                row.append("" if value is None else f"{value:.17g}")
            writer.writerow(row)


def write_summary_csv(summary: Dict[str, Dict[str, float]], output_path: pathlib.Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Currency", "Observations", "Average Weekly Log Change (%)", "Std Dev Weekly Log Change (%)"])
        for currency, stats in summary.items():
            writer.writerow(
                [
                    currency,
                    stats["observations"],
                    "" if stats["average_weekly_percent_change"] is None else f"{stats['average_weekly_percent_change']:.6f}",
                    "" if stats["std_dev_weekly_percent_change"] is None else f"{stats['std_dev_weekly_percent_change']:.6f}",
                ]
            )


def correlation_matrices(changes):
    """Pair on actual dates, never row position; also return pairwise sample sizes."""
    by_date = {}
    for currency, series in changes.items():
        mapping = dict(series)
        if len(mapping) != len(series):
            raise DataQualityError(f"{currency}: duplicate return dates.")
        by_date[currency] = mapping
    correlations, counts = {}, {}
    for currency, left in by_date.items():
        correlations[currency], counts[currency] = {}, {}
        for other, right in by_date.items():
            pairs = [(left[d], right[d]) for d in sorted(left.keys() & right.keys())
                     if left[d] is not None and right[d] is not None]
            counts[currency][other] = len(pairs)
            try:
                value = statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
            except statistics.StatisticsError:
                value = None  # Fewer than two pairs or constant series.
            correlations[currency][other] = value
    return correlations, counts


def write_matrix_csv(matrix, output_path):
    currencies = list(matrix)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Currency", *currencies])
        for currency in currencies:
            writer.writerow([currency, *["" if matrix[currency][c] is None
                                         else matrix[currency][c] for c in currencies]])


def write_correlation_matrix_csv(percent_changes, output_path):
    write_matrix_csv(correlation_matrices(percent_changes)[0], output_path)


def plot_series_svg(
    dates: List[dt.date],
    values: List[Optional[float]],
    currency: str,
    output_path: pathlib.Path,
    width: int = 1200,
    height: int = 600,
    padding: int = 90,
) -> None:
    points = [(idx, value) for idx, value in enumerate(values) if value is not None]
    if not points:
        return

    y_values = [point[1] for point in points]

    min_x, max_x = 0, len(dates) - 1
    min_y, max_y = min(y_values), max(y_values)

    if math.isclose(min_y, max_y):
        min_y -= 1
        max_y += 1

    plot_width = width - 2 * padding
    plot_height = height - 2 * padding

    def scale_x(x_value: int) -> float:
        if max_x == min_x:
            return padding + plot_width / 2
        return padding + (x_value - min_x) / (max_x - min_x) * plot_width

    def scale_y(y_value: float) -> float:
        return padding + (max_y - y_value) / (max_y - min_y) * plot_height

    # Separate segments at missing quotes; never draw across unavailable observations.
    segments, segment = [], []
    for idx, value in enumerate(values):
        if value is None:
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(f"{scale_x(idx):.2f},{scale_y(value):.2f}")
    if segment:
        segments.append(segment)
    polylines = "\n".join(
        '<polyline points="' + ' '.join(points) + '" fill="none" stroke="#2f6fb0" stroke-width="2" />'
        for points in segments
    )
    title = escape(f"{currency} Weekly Exchange Rate | {dates[0]} to {dates[-1]}")
    start_year = dates[0].year
    end_year = dates[-1].year
    tick_start_year = (start_year // 5) * 5
    year_ticks = list(range(tick_start_year, end_year + 1, 5))
    if year_ticks and year_ticks[0] < start_year:
        year_ticks = year_ticks[1:]

    year_tick_labels = []
    for year in year_ticks:
        tick_dates = [index for index, date_value in enumerate(dates) if date_value.year == year]
        if not tick_dates:
            continue
        x_position = scale_x(tick_dates[0])
        year_tick_labels.append((year, x_position))

    y_tick_count = 10
    y_step = (max_y - min_y) / y_tick_count
    y_ticks = [min_y + y_step * i for i in range(y_tick_count + 1)]
    y_tick_labels = [(value, scale_y(value)) for value in y_ticks]

    vertical_gridlines = "\n".join(
        f"  <line x1=\"{x_position:.2f}\" y1=\"{padding}\" x2=\"{x_position:.2f}\" y2=\"{height - padding}\" stroke=\"#e0e0e0\" stroke-width=\"1\" />"
        for _, x_position in year_tick_labels
    )
    horizontal_gridlines = "\n".join(
        f"  <line x1=\"{padding}\" y1=\"{y_position:.2f}\" x2=\"{width - padding}\" y2=\"{y_position:.2f}\" stroke=\"#e0e0e0\" stroke-width=\"1\" />"
        for _, y_position in y_tick_labels
    )

    y_axis_labels = "\n".join(
        f"  <text x=\"{padding - 8}\" y=\"{y_position + 4:.2f}\" font-size=\"12\" text-anchor=\"end\" fill=\"#444\">{value:.6g}</text>"
        for value, y_position in y_tick_labels
    )

    tick_label_elements = "\n".join(
        f"  <text x=\"{x_position:.2f}\" y=\"{height - padding / 2}\" font-size=\"12\" text-anchor=\"middle\" fill=\"#444\">{year}</text>"
        for year, x_position in year_tick_labels
    )

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <rect width="100%" height="100%" fill="white" />
{vertical_gridlines}
{horizontal_gridlines}
  <text x="{width / 2}" y="{padding / 2}" font-size="20" text-anchor="middle" fill="#222">{title}</text>
{polylines}
{tick_label_elements}
{y_axis_labels}
  <text x="{width / 2}" y="{height - 10}" font-size="14" text-anchor="middle" fill="#222">Year</text>
  <text x="20" y="{height / 2}" font-size="14" text-anchor="middle" fill="#222" transform="rotate(-90, 20, {height / 2})">USD quote (source scale)</text>
  <text x="{padding}" y="{padding}" font-size="12" fill="#444">Max: {max_y:.6g}</text>
  <text x="{padding}" y="{padding + 16}" font-size="12" fill="#444">Min: {min_y:.6g}</text>
</svg>
"""
    output_path.write_text(svg_content, encoding="utf-8")


def plot_exchange_rates(
    dates: List[dt.date],
    data: Dict[str, List[Optional[float]]],
    plots_dir: pathlib.Path,
) -> None:
    plots_dir.mkdir(parents=True, exist_ok=True)
    for currency, values in data.items():
        output_path = plots_dir / f"{currency}.svg"
        plot_series_svg(dates, values, currency, output_path)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Validated weekly Bloomberg log-return analysis.")
    parser.add_argument("--input", type=pathlib.Path, default=DATA_FILE)
    parser.add_argument("--output-dir", type=pathlib.Path, default=OUTPUT_DIR)
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=None,
                        help="ISO assessment date; defaults to today's UTC date, never an observation date.")
    parser.add_argument("--max-age-days", type=int, default=14)
    parser.add_argument("--require-current", action="store_true", help="Fail if observations are stale.")
    parser.add_argument("--strict-missing", action="store_true", help="Fail on any missing quote.")
    args = parser.parse_args(argv)
    dates, data = load_exchange_rates(args.input, strict_missing=args.strict_missing)
    metadata = provenance(args.input, dates, data, as_of=args.as_of, max_age_days=args.max_age_days)
    if metadata["stale"]:
        message = f"HISTORICAL DATA: observations end {dates[-1]}, {metadata['age_days']} days before {metadata['as_of']}."
        if args.require_current:
            parser.error(message)
        print(message)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    changes = compute_weekly_log_changes(dates, data)
    write_summary_csv(summarize_percent_changes(changes), output / "weekly_log_change_stats_full.csv")
    write_summary_csv(summarize_percent_changes(changes, dt.date(2008, 1, 1), dt.date(2009, 12, 31)),
                      output / "weekly_log_change_stats_2008_2009.csv")
    write_percent_changes_csv(dates, changes, output / "weekly_log_changes.csv")
    correlations, counts = correlation_matrices(changes)
    write_matrix_csv(correlations, output / "weekly_log_change_correlation.csv")
    write_matrix_csv(counts, output / "weekly_log_change_correlation_counts.csv")
    plot_exchange_rates(dates, data, output / "plots")
    (output / "analysis_manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Saved log-return statistics, correlations, counts, metadata and plots to {output}")
    print(f"Actual observations: {dates[0]} to {dates[-1]} ({len(dates)} weeks).")


if __name__ == "__main__":
    main()
