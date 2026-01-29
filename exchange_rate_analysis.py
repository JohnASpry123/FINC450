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


def compute_weekly_percent_changes(
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
            if previous == 0:
                series.append((date_value, None))
                previous = current
                continue
            change = ((current / previous) - 1) * 100
            series.append((date_value, change))
            previous = current
        percent_changes[currency] = series
    return percent_changes


def summarize_percent_changes(
    percent_changes: Dict[str, List[Tuple[dt.date, Optional[float]]]]
) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    for currency, series in percent_changes.items():
        values = [value for _, value in series if value is not None]
        if not values:
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

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <rect width="100%" height="100%" fill="white" />
  <text x="{width / 2}" y="{padding / 2}" font-size="20" text-anchor="middle" fill="#222">{title}</text>
  <polyline points="{polyline_points}" fill="none" stroke="#2f6fb0" stroke-width="2" />
  <text x="{padding}" y="{height - padding / 2}" font-size="12" fill="#444">{start_date}</text>
  <text x="{width - padding}" y="{height - padding / 2}" font-size="12" text-anchor="end" fill="#444">{end_date}</text>
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
    percent_changes = compute_weekly_percent_changes(dates, data)
    summary = summarize_percent_changes(percent_changes)

    summary_path = OUTPUT_DIR / "weekly_percent_change_stats.csv"
    pct_path = OUTPUT_DIR / "weekly_percent_changes.csv"

    write_summary_csv(summary, summary_path)
    write_percent_changes_csv(dates, percent_changes, pct_path)
    plot_exchange_rates(dates, data, PLOTS_DIR)

    print(f"Saved summary statistics to {summary_path}")
    print(f"Saved weekly percent changes to {pct_path}")
    print(f"Saved plots to {PLOTS_DIR}")


if __name__ == "__main__":
    main()
