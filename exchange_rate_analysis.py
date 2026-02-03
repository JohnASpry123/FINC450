import csv
import datetime as dt
import math
import pathlib
import statistics
from typing import Dict, List, Optional, Tuple


DATA_FILE = "Bloomberg Weekly Exchange Rates since 2000 1 28 2026.cvs.csv"
OUTPUT_DIR = pathlib.Path("outputs")
PLOTS_DIR = OUTPUT_DIR / "plots"


def parse_float(value: str) -> Optional[float]:
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_exchange_rates(csv_path: str) -> Tuple[List[dt.date], Dict[str, List[Optional[float]]]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        currencies = [field for field in reader.fieldnames if field != "Date"]
        dates: List[dt.date] = []
        data: Dict[str, List[Optional[float]]] = {currency: [] for currency in currencies}
        for row in reader:
            if row.get("Date") in (None, "", "(auto)"):
                continue
            try:
                date_value = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date()
            except ValueError:
                continue
            dates.append(date_value)
            for currency in currencies:
                data[currency].append(parse_float(row.get(currency, "")))
    return dates, data


def compute_weekly_log_changes(
    dates: List[dt.date],
    data: Dict[str, List[Optional[float]]],
) -> Dict[str, List[Tuple[dt.date, Optional[float]]]]:
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]] = {}
    for currency, values in data.items():
        series: List[Tuple[dt.date, Optional[float]]] = []
        previous: Optional[float] = None
        for date_value, current in zip(dates, values):
            if current is None or previous is None:
                series.append((date_value, None))
                previous = current
                continue
            if previous <= 0 or current <= 0:
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
        if len(values) < 2:
            continue
        summary[currency] = {
            "average_weekly_percent_change": statistics.fmean(values),
            "std_dev_weekly_percent_change": statistics.stdev(values),
        }
    return summary


def write_percent_changes_csv(
    dates: List[dt.date],
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]],
    output_path: pathlib.Path,
) -> None:
    currencies = list(percent_changes.keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", *currencies])
        for idx, date_value in enumerate(dates):
            row = [date_value.isoformat()]
            for currency in currencies:
                value = percent_changes[currency][idx][1]
                row.append("" if value is None else f"{value:.6f}")
            writer.writerow(row)


def write_summary_csv(summary: Dict[str, Dict[str, float]], output_path: pathlib.Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Currency", "Average Weekly % Change", "Std Dev Weekly % Change"])
        for currency, stats in summary.items():
            writer.writerow(
                [
                    currency,
                    f"{stats['average_weekly_percent_change']:.6f}",
                    f"{stats['std_dev_weekly_percent_change']:.6f}",
                ]
            )


def write_correlation_matrix_csv(
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]],
    output_path: pathlib.Path,
) -> None:
    currencies = list(percent_changes.keys())
    values_by_currency = {
        currency: [value for _, value in series]
        for currency, series in percent_changes.items()
    }

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Currency", *currencies])
        for currency in currencies:
            row = [currency]
            base_values = values_by_currency[currency]
            for other_currency in currencies:
                other_values = values_by_currency[other_currency]
                paired = [
                    (left, right)
                    for left, right in zip(base_values, other_values)
                    if left is not None and right is not None
                ]
                if len(paired) < 2:
                    row.append("")
                    continue
                left_values = [pair[0] for pair in paired]
                right_values = [pair[1] for pair in paired]
                try:
                    correlation = statistics.correlation(left_values, right_values)
                except statistics.StatisticsError:
                    row.append("")
                    continue
                row.append(f"{correlation:.6f}")
            writer.writerow(row)


def plot_series_svg(
    dates: List[dt.date],
    values: List[Optional[float]],
    currency: str,
    output_path: pathlib.Path,
    width: int = 1200,
    height: int = 600,
    padding: int = 50,
) -> None:
    points = [(idx, value) for idx, value in enumerate(values) if value is not None]
    if not points:
        return

    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]

    min_x, max_x = min(x_values), max(x_values)
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

    polyline_points = " ".join(
        f"{scale_x(x_value):.2f},{scale_y(y_value):.2f}" for x_value, y_value in points
    )

    title = f"{currency} Weekly Exchange Rate"
    start_date = dates[0].isoformat()
    end_date = dates[-1].isoformat()
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
        f"  <text x=\"{padding - 8}\" y=\"{y_position + 4:.2f}\" font-size=\"12\" text-anchor=\"end\" fill=\"#444\">{value:.4f}</text>"
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
  <polyline points="{polyline_points}" fill="none" stroke="#2f6fb0" stroke-width="2" />
{tick_label_elements}
{y_axis_labels}
  <text x="{width / 2}" y="{height - 10}" font-size="14" text-anchor="middle" fill="#222">Year</text>
  <text x="20" y="{height / 2}" font-size="14" text-anchor="middle" fill="#222" transform="rotate(-90, 20, {height / 2})">Exchange Rate</text>
  <text x="{padding}" y="{padding}" font-size="12" fill="#444">Max: {max_y:.4f}</text>
  <text x="{padding}" y="{padding + 16}" font-size="12" fill="#444">Min: {min_y:.4f}</text>
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


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dates, data = load_exchange_rates(DATA_FILE)
    percent_changes = compute_weekly_log_changes(dates, data)
    summary_full = summarize_percent_changes(percent_changes)
    summary_crisis = summarize_percent_changes(
        percent_changes,
        start_date=dt.date(2008, 1, 1),
        end_date=dt.date(2009, 12, 31),
    )

    summary_path = OUTPUT_DIR / "weekly_log_change_stats_full.csv"
    summary_crisis_path = OUTPUT_DIR / "weekly_log_change_stats_2008_2009.csv"
    pct_path = OUTPUT_DIR / "weekly_log_changes.csv"
    correlation_path = OUTPUT_DIR / "weekly_log_change_correlation.csv"

    write_summary_csv(summary_full, summary_path)
    write_summary_csv(summary_crisis, summary_crisis_path)
    write_percent_changes_csv(dates, percent_changes, pct_path)
    write_correlation_matrix_csv(percent_changes, correlation_path)
    plot_exchange_rates(dates, data, PLOTS_DIR)

    print(f"Saved summary statistics to {summary_path}")
    print(f"Saved 2008-2009 summary statistics to {summary_crisis_path}")
    print(f"Saved weekly percent changes to {pct_path}")
    print(f"Saved correlation matrix to {correlation_path}")
    print(f"Saved plots to {PLOTS_DIR}")


if __name__ == "__main__":
    main()
