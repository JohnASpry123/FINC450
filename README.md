# FINC450

FINC 450 for Downloading Exchange Rate Data from FRED

## Usage

1. Install the required libraries:

   ```bash
   pip install pandas numpy matplotlib fredapi
   ```

2. Set your FRED API key as an environment variable:

   ```bash
   export FRED_API_KEY=your_api_key_here
   ```

3. Run the script to download data, generate charts and export an Excel file:

   ```bash
   python exchange_rates.py
   ```

The resulting spreadsheet will be saved as `exchange_rates.xlsx`.

## Weekly exchange rate analysis

To calculate weekly percentage changes, summary statistics, and generate per-currency
plots for the Bloomberg weekly dataset:

```bash
python exchange_rate_analysis.py
```

Outputs are saved in the `outputs/` directory (including plots in `outputs/plots`).

## Load the Bloomberg weekly XLSX with full precision

The repository includes `Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx`.
Use the loader below to export a CSV copy that preserves every cell value as text
(no float coercion):

```bash
python bloomberg_weekly_loader.py \
  --xlsx "Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx" \
  --output outputs/bloomberg_weekly_exchange_rates.csv
```

The generated CSV is saved to `outputs/bloomberg_weekly_exchange_rates.csv` for
analysis or ingestion in other tools.
