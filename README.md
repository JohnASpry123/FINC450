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
