import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from fredapi import Fred


def plot_pair(series1, series2, label1, label2, title, colors=None):
    """Plot a pair of exchange rate series."""
    plt.figure(figsize=(12, 8))
    if colors is None:
        plt.plot(series1, label=label1)
        plt.plot(series2, label=label2)
    else:
        plt.plot(series1, label=label1, color=colors[0])
        plt.plot(series2, label=label2, color=colors[1])
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Exchange Rate")
    plt.legend()
    plt.grid(True)
    min_val = min(series1.min(), series2.min())
    max_val = max(series1.max(), series2.max())
    plt.yticks(np.around(np.arange(min_val, max_val, 0.10), 1))
    plt.ylim(0)
    plt.show()


def main():
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY environment variable not set")

    fred = Fred(api_key=api_key)

    # Euro
    eurusd = fred.get_series("DEXUSEU").dropna()
    usdeur = 1 / eurusd
    plot_pair(eurusd, usdeur, "EUR/USD (USD per 1 EUR)", "USD/EUR (EUR per 1 USD)",
              "EUR/USD and USD/EUR Exchange Rates")

    # Canadian Dollar
    cadusd = fred.get_series("DEXCAUS").dropna()
    usdcad = 1 / cadusd
    plot_pair(cadusd, usdcad, "CAD/USD (CAD per 1 USD)", "USD/CAD (USD per 1 CAD)",
              "CAD/USD and USD/CAD Exchange Rates", colors=("orange", "blue"))

    # Japanese Yen
    jpyusd = fred.get_series("DEXJPUS").dropna()
    usdjpy = 1 / jpyusd
    plt.figure(figsize=(12, 8))
    plt.plot(jpyusd, label="JPY/USD (JPY per 1 USD)", color="red")
    plt.title("JPY/USD Exchange Rate")
    plt.xlabel("Date")
    plt.ylabel("Exchange Rate")
    plt.legend()
    plt.grid(True)
    plt.ylim(0)
    plt.show()

    plt.figure(figsize=(12, 8))
    plt.plot(usdjpy, label="USD/JPY (USD per 1 JPY)", color="green")
    plt.title("USD/JPY Exchange Rate")
    plt.xlabel("Date")
    plt.ylabel("Exchange Rate")
    plt.legend()
    plt.grid(True)
    plt.ylim(0)
    plt.show()

    # British Pound
    usdgbp = fred.get_series("DEXUSUK").dropna()
    gbpusd = 1 / usdgbp
    plot_pair(usdgbp, gbpusd, "USD/GBP (USD per 1 GBP)", "GBP/USD (GBP per 1 USD)",
              "GBP/USD and USD/GBP Exchange Rates")

    all_exchange_rates = pd.DataFrame({
        "EUR/USD": eurusd,
        "USD/EUR": usdeur,
        "CAD/USD": cadusd,
        "USD/CAD": usdcad,
        "JPY/USD": jpyusd,
        "USD/JPY": usdjpy,
        "USD/GBP": usdgbp,
        "GBP/USD": gbpusd,
    })

    excel_file_path = "exchange_rates.xlsx"
    with pd.ExcelWriter(excel_file_path) as writer:
        all_exchange_rates.to_excel(writer, sheet_name="Exchange Rates")
    print(f"Exchange rates exported to {excel_file_path}")


if __name__ == "__main__":
    main()
