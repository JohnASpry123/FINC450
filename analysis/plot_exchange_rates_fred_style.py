"""Generate publication-sized exchange-rate figures from the shared validated input."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from fx_data import DEFAULT_INPUT, ROOT, load_exchange_rates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'figures')
    args = parser.parse_args(argv)
    dates, data = load_exchange_rates(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for currency, values in data.items():
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(dates, [float('nan') if v is None else v for v in values], color='#2f5597', lw=1.5)
        ax.yaxis.grid(True, color='#d9d9d9', lw=.8)
        ax.spines[['top', 'right']].set_visible(False)
        ax.tick_params(labelsize=13)
        ax.set_xlabel('Date', fontsize=15)
        ax.set_ylabel('USD quote (source scale)', fontsize=15)
        ax.set_title(f'{currency} Weekly Exchange Rate', fontsize=20, pad=15)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.ticklabel_format(axis='y', style='plain', useOffset=False)
        fig.text(.5, .02, f'Bloomberg | Observations: {dates[0]} to {dates[-1]} | Gaps = missing quotes',
                 ha='center', fontsize=12)
        fig.tight_layout(rect=[0, .06, 1, 1])
        fig.savefig(args.output_dir / f'{currency}_exchange_rate.png', dpi=160)
        plt.close(fig)


if __name__ == '__main__':
    main()
