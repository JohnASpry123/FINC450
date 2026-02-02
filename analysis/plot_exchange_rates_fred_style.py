"""Generate FRED-style exchange rate line graphs from Bloomberg weekly data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


DATA_PATH = Path("outputs/bloomberg_weekly_exchange_rates.csv")
OUTPUT_DIR = Path("figures")


def find_date_column(columns: list[str]) -> str:
    """Return the name of the date column based on common patterns."""
    for column in columns:
        if "date" in column.lower():
            return column
    return columns[0]


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse a date series, handling Excel serials when needed."""
    series = series.copy()
    numeric_series = pd.to_numeric(series, errors="coerce")
    if numeric_series.notna().all():
        return pd.to_datetime(numeric_series, unit="D", origin="1899-12-30")
    return pd.to_datetime(series, errors="coerce")


def style_axes(ax: plt.Axes) -> None:
    """Apply FRED-like styling to axes."""
    ax.set_facecolor("white")
    ax.yaxis.grid(True, color="#d9d9d9", linewidth=0.8)
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=11)


def plot_exchange_rates(data: pd.DataFrame, date_column: str) -> None:
    """Create one FRED-style figure per exchange rate series."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for column in data.columns:
        if column == date_column:
            continue

        series = pd.to_numeric(data[column], errors="coerce")
        fig, ax = plt.subplots(figsize=(10, 5.5))
        ax.plot(
            data[date_column],
            series,
            color="#2f5597",
            linewidth=2.0,
        )

        style_axes(ax)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Units of foreign currency per U.S. dollar", fontsize=12)
        ax.set_title(f"{column} Exchange Rate (Weekly)", fontsize=14, pad=20)
        fig.text(0.5, 0.92, "Source: Bloomberg", ha="center", fontsize=11)

        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        fig.autofmt_xdate(rotation=45)

        output_path = OUTPUT_DIR / f"{column}_exchange_rate.png"
        fig.tight_layout(rect=[0, 0, 1, 0.92])
        fig.savefig(output_path, dpi=300)
        plt.close(fig)


def main() -> None:
    """Load data and produce exchange rate figures."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {DATA_PATH}")

    data = pd.read_csv(DATA_PATH)
    date_column = find_date_column(list(data.columns))
    data[date_column] = parse_dates(data[date_column])
    data = data.dropna(subset=[date_column]).sort_values(date_column)

    plot_exchange_rates(data, date_column)


if __name__ == "__main__":
    main()
