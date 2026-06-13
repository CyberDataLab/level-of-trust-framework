import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


DEFAULT_PATTERNS = [
    '*host_timeseries*.csv',
    '*timeseries*.csv',
]

METRICS = ['health_score', 'level_of_trust', 'historical_average']


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


def load_data(files):
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
        raise FileNotFoundError('No readable CSV files found.')

    df = pd.concat(frames, ignore_index=True)

    if 'timestamp' in df.columns:
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')

    for col in ['elapsed_sec', 'health_score', 'level_of_trust', 'historical_average']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def summarize_assets(df):
    rows = []
    grouped = df.groupby(['host', 'asset_id'], dropna=False)

    for (host, asset_id), g in grouped:
        row = {
            'host': host,
            'asset_id': asset_id,
            'samples': len(g),
        }

        for metric in ['health_score', 'level_of_trust']:
            vals = g[metric].dropna()
            if len(vals) == 0:
                row[f'{metric}_mean'] = None
                row[f'{metric}_median'] = None
                row[f'{metric}_min'] = None
                row[f'{metric}_max'] = None
                row[f'{metric}_std'] = None
            else:
                row[f'{metric}_mean'] = vals.mean()
                row[f'{metric}_median'] = vals.median()
                row[f'{metric}_min'] = vals.min()
                row[f'{metric}_max'] = vals.max()
                row[f'{metric}_std'] = vals.std()

        row['health_below_100_samples'] = (g['health_score'] < 100).sum()
        row['lot_below_100_samples'] = (g['level_of_trust'] < 100).sum()

        if 'elapsed_sec' in g.columns and g['elapsed_sec'].notna().any():
            g_sorted = g.sort_values('elapsed_sec')
            if len(g_sorted) > 1:
                diffs = g_sorted['elapsed_sec'].diff().dropna()
                sample_period = diffs.median() if len(diffs) else None
            else:
                sample_period = None

            if sample_period is not None:
                row['health_below_100_time_sec_est'] = row['health_below_100_samples'] * sample_period
                row['lot_below_100_time_sec_est'] = row['lot_below_100_samples'] * sample_period
            else:
                row['health_below_100_time_sec_est'] = None
                row['lot_below_100_time_sec_est'] = None
        else:
            row['health_below_100_time_sec_est'] = None
            row['lot_below_100_time_sec_est'] = None

        rows.append(row)

    out = pd.DataFrame(rows)
    return out.sort_values(['host', 'health_score_min', 'level_of_trust_min'], ascending=[True, True, True])


def detect_events(df):
    event_rows = []

    grouped = df.groupby(['host', 'asset_id'], dropna=False)
    for (host, asset_id), g in grouped:
        g = g.sort_values('elapsed_sec').copy()

        for metric in ['health_score', 'level_of_trust']:
            below = g[metric] < 100
            if not below.any():
                continue

            start_idx = None
            for i, is_bad in enumerate(below.tolist()):
                if is_bad and start_idx is None:
                    start_idx = i
                elif not is_bad and start_idx is not None:
                    segment = g.iloc[start_idx:i]
                    event_rows.append(build_event_row(host, asset_id, metric, segment))
                    start_idx = None

            if start_idx is not None:
                segment = g.iloc[start_idx:]
                event_rows.append(build_event_row(host, asset_id, metric, segment))

    if not event_rows:
        return pd.DataFrame(columns=[
            'host', 'asset_id', 'metric', 'start_elapsed_sec', 'end_elapsed_sec',
            'duration_sec_est', 'min_value', 'mean_value', 'start_timestamp', 'end_timestamp'
        ])

    return pd.DataFrame(event_rows).sort_values(['host', 'start_elapsed_sec', 'asset_id'])


def build_event_row(host, asset_id, metric, segment):
    start_elapsed = segment['elapsed_sec'].iloc[0] if 'elapsed_sec' in segment.columns else None
    end_elapsed = segment['elapsed_sec'].iloc[-1] if 'elapsed_sec' in segment.columns else None

    duration = None
    if start_elapsed is not None and end_elapsed is not None and len(segment) > 1:
        diffs = segment['elapsed_sec'].diff().dropna()
        median_step = diffs.median() if len(diffs) else 0
        duration = (end_elapsed - start_elapsed) + median_step
    elif start_elapsed is not None and end_elapsed is not None:
        duration = 0

    return {
        'host': host,
        'asset_id': asset_id,
        'metric': metric,
        'start_elapsed_sec': start_elapsed,
        'end_elapsed_sec': end_elapsed,
        'duration_sec_est': duration,
        'min_value': segment[metric].min(),
        'mean_value': segment[metric].mean(),
        'start_timestamp': segment['timestamp_dt'].iloc[0] if 'timestamp_dt' in segment.columns else None,
        'end_timestamp': segment['timestamp_dt'].iloc[-1] if 'timestamp_dt' in segment.columns else None,
    }


def worst_points(df):
    rows = []

    grouped = df.groupby(['host', 'asset_id'], dropna=False)
    for (host, asset_id), g in grouped:
        for metric in ['health_score', 'level_of_trust']:
            idx = g[metric].idxmin()
            row = g.loc[idx]
            rows.append({
                'host': host,
                'asset_id': asset_id,
                'metric': metric,
                'worst_value': row[metric],
                'elapsed_sec': row.get('elapsed_sec'),
                'timestamp_dt': row.get('timestamp_dt'),
                'historical_average': row.get('historical_average'),
                'source_file': row.get('source_file'),
            })

    return pd.DataFrame(rows).sort_values(['host', 'metric', 'worst_value'])


def top_degraded_assets(asset_summary, top_n=8):
    degraded = asset_summary[
        (asset_summary['health_score_min'] < 100) |
        (asset_summary['level_of_trust_min'] < 100)
    ].copy()

    if degraded.empty:
        return []

    degraded['severity_rank'] = degraded[['health_score_min', 'level_of_trust_min']].min(axis=1)
    degraded = degraded.sort_values(['severity_rank', 'lot_below_100_samples', 'health_below_100_samples'])
    return degraded['asset_id'].head(top_n).tolist()


def plot_metric(df, assets, metric, output_name, title):
    if not assets:
        print(f'INFO: no assets selected for {output_name}')
        return

    plt.figure(figsize=(14, 7))

    for asset in assets:
        g = df[df['asset_id'] == asset].sort_values('elapsed_sec')
        if g.empty:
            continue
        plt.plot(g['elapsed_sec'], g[metric], marker='o', linewidth=1.5, markersize=3, label=asset)

    plt.xlabel('Elapsed time (s)', fontsize=18)
    plt.ylabel(metric.replace('_', ' ').title(), fontsize=18)
    plt.title(title, fontsize=18)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=12)
    plt.xticks(fontsize=14)
    plt.yticks(fontsize=14)
    plt.tight_layout()
    plt.savefig(output_name, dpi=200)
    plt.close()


def plot_node_overview(df, output_name):
    root_assets = df[df['asset_id'].str.fullmatch(r'/node\[name=[^\]]+\]', na=False)].copy()

    if root_assets.empty:
        print(f'INFO: no root node assets found for {output_name}')
        return

    root_assets = root_assets.sort_values(['host', 'elapsed_sec'])

    # Si por cualquier motivo hubiera más de una fila del root por host+instante,
    # nos quedamos con una sola para evitar líneas espurias.
    root_assets = root_assets.drop_duplicates(subset=['host', 'elapsed_sec'], keep='first')

    plt.figure(figsize=(14, 7))

    for host, g in root_assets.groupby('host'):
        g = g.sort_values('elapsed_sec')
        plt.plot(
            g['elapsed_sec'],
            g['level_of_trust'],
            marker='o',
            linewidth=2,
            markersize=3,
            label=f'{host} LoT'
        )
        plt.plot(
            g['elapsed_sec'],
            g['health_score'],
            marker='s',
            linestyle='--',
            linewidth=1.5,
            markersize=3,
            label=f'{host} Health'
        )

    plt.xlabel('Elapsed time (s)', fontsize=12)
    plt.ylabel('Score')
    plt.title('Root node health score and level of trust over time')
    plt.ylim(0, 105)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_name, dpi=200)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Analyze host timeseries CSV files.')
    parser.add_argument('-f', '--files', nargs='*', help='Input CSV files')
    parser.add_argument('--prefix', default='timeseries', help='Prefix for output files')
    parser.add_argument('--top-n', type=int, default=8, help='Top degraded assets to plot')
    args = parser.parse_args()

    files = [Path(f) for f in args.files] if args.files else discover_files()
    if not files:
        raise FileNotFoundError('No CSV files found. Use -f host1_host_timeseries.csv host2_host_timeseries.csv')

    print('Input files:')
    for f in files:
        print(f'  - {f}')

    df = load_data(files)

    required_cols = {'host', 'asset_id', 'health_score', 'level_of_trust'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')

    combined_output = f'{args.prefix}_combined.csv'
    asset_summary_output = f'{args.prefix}_asset_summary.csv'
    events_output = f'{args.prefix}_events.csv'
    worst_output = f'{args.prefix}_worst_points.csv'
    root_plot_output = f'{args.prefix}_root_overview.png'
    health_plot_output = f'{args.prefix}_top_assets_health.png'
    lot_plot_output = f'{args.prefix}_top_assets_lot.png'

    df.to_csv(combined_output, index=False)

    asset_summary = summarize_assets(df)
    asset_summary.to_csv(asset_summary_output, index=False)

    events = detect_events(df)
    events.to_csv(events_output, index=False)

    worst = worst_points(df)
    worst.to_csv(worst_output, index=False)

    selected_assets = top_degraded_assets(asset_summary, top_n=args.top_n)
    plot_node_overview(df, root_plot_output)
    plot_metric(df, selected_assets, 'health_score', health_plot_output, 'Health score of most degraded assets')
    plot_metric(df, selected_assets, 'level_of_trust', lot_plot_output, 'Level of trust of most degraded assets')

    print('\nTop degraded assets selected for plots:')
    for asset in selected_assets:
        print(f'  - {asset}')

    print('\nFiles generated:')
    print(f'  - {combined_output}')
    print(f'  - {asset_summary_output}')
    print(f'  - {events_output}')
    print(f'  - {worst_output}')
    print(f'  - {root_plot_output}')
    print(f'  - {health_plot_output}')
    print(f'  - {lot_plot_output}')


if __name__ == '__main__':
    main()