import argparse
from pathlib import Path
import pandas as pd

DEFAULT_METRICS = [
    'kafka_processing_time_ms',
    'kg_mapping_time_ms',
    'kg_load_time_ms',
    'kg_total_time_ms',
    'end_to_end_time_ms',
]

DEFAULT_PATTERNS = [
    '*performance*.csv',
    '*.csv',
]


def percentile(q):
    def _p(series):
        return series.quantile(q)
    _p.__name__ = f'p{int(q * 100)}'
    return _p


def build_summary(df, metrics, extra_group_col=None):
    agg_funcs = ['count', 'mean', 'std', 'min', percentile(0.90), percentile(0.95), percentile(0.99), 'median', 'max']

    if extra_group_col:
        rows = []
        for group_value, g in df.groupby(extra_group_col):
            s = g[metrics].agg(agg_funcs).T.reset_index()
            s = s.rename(columns={'index': 'metric'})
            s[extra_group_col] = group_value
            s['unit'] = 'ms'
            rows.append(s)
        if not rows:
            return pd.DataFrame()
        return pd.concat(rows, ignore_index=True).round(3)

    s = df[metrics].agg(agg_funcs).T.reset_index()
    s = s.rename(columns={'index': 'metric'})
    s['unit'] = 'ms'
    return s.round(3)


def discover_files():
    found = []
    for pattern in DEFAULT_PATTERNS:
        matches = sorted(Path('.').glob(pattern))
        matches = [p for p in matches if p.is_file()]
        if matches:
            found.extend(matches)
            break
    unique = []
    seen = set()
    for f in found:
        if f.name not in seen:
            seen.add(f.name)
            unique.append(f)
    return unique


def load_files(files):
    frames = []
    for f in files:
        if not f.exists():
            print(f'WARNING: file not found: {f}')
            continue
        try:
            df = pd.read_csv(f)
            df['source_file'] = f.name
            frames.append(df)
        except Exception as e:
            print(f'WARNING: could not read {f}: {e}')
    if not frames:
        raise FileNotFoundError(
            'No readable CSV files found. Pass them explicitly with -f or place performance CSV files in this folder.'
        )
    return pd.concat(frames, ignore_index=True)


def validate_metrics(df, metrics):
    available = [m for m in metrics if m in df.columns]
    missing = [m for m in metrics if m not in df.columns]

    if missing:
        print('WARNING: missing metrics:')
        for m in missing:
            print(f'  - {m}')

    if not available:
        raise ValueError('None of the expected metric columns were found in the input data.')

    return available


def main():
    parser = argparse.ArgumentParser(
        description='Compute performance statistics from one or more CSV files.'
    )
    parser.add_argument(
        '-f', '--files',
        nargs='*',
        help='Input CSV files, e.g. host1_performance.csv host2_performance.csv'
    )
    parser.add_argument(
        '-m', '--metrics',
        nargs='*',
        default=DEFAULT_METRICS,
        help='Metric columns to summarize'
    )
    parser.add_argument(
        '--prefix',
        default='performance',
        help='Prefix for output files'
    )
    args = parser.parse_args()

    input_files = [Path(f) for f in args.files] if args.files else discover_files()

    if not input_files:
        raise FileNotFoundError(
            'No CSV files found automatically. Use -f host1_performance.csv host2_performance.csv'
        )

    print('Input files:')
    for f in input_files:
        print(f'  - {f}')

    combined = load_files(input_files)
    metrics = validate_metrics(combined, args.metrics)

    combined_output = f'{args.prefix}_combined.csv'
    summary_combined_output = f'{args.prefix}_summary_combined.csv'
    summary_per_file_output = f'{args.prefix}_summary_per_file.csv'
    summary_per_host_output = f'{args.prefix}_summary_per_host.csv'

    combined.to_csv(combined_output, index=False)

    summary_combined = build_summary(combined, metrics)
    summary_combined.to_csv(summary_combined_output, index=False)

    summary_per_file = build_summary(combined, metrics, extra_group_col='source_file')
    summary_per_file.to_csv(summary_per_file_output, index=False)

    if 'host' in combined.columns:
        summary_per_host = build_summary(combined, metrics, extra_group_col='host')
        summary_per_host.to_csv(summary_per_host_output, index=False)
    else:
        summary_per_host = None
        print("INFO: column 'host' not found, skipping per-host summary.")

    print('\n=== Combined summary ===')
    print(summary_combined.to_string(index=False))

    print('\nFiles generated:')
    print(f'  - {combined_output}')
    print(f'  - {summary_combined_output}')
    print(f'  - {summary_per_file_output}')
    if summary_per_host is not None:
        print(f'  - {summary_per_host_output}')


if __name__ == '__main__':
    main()