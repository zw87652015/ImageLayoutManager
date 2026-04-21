"""
Standalone Violin Plot Generator for Nature Communications
Reads CSV data and generates publication-quality violin plots.

Usage:
    python violin_plot_generator.py input.csv --value ValueCol --group GroupCol --output figure.pdf
    python violin_plot_generator.py input.csv -v 0 -o figure.pdf
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats


# Wong / Okabe-Ito colorblind-safe palette
WONG_PALETTE = [
    '#000000', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#0072B2', '#D55E00', '#CC79A7'
]

# Additional color themes
THEME_BLUE_PINK = [
    '#104e8b', '#376b9e', '#5f89b1', '#afc3d8', '#c5e9e3',
    '#d7e1eb', '#f2dada', '#e5b5b5', '#d89090', '#b22222'
]

THEME_BLUE_RED = [
    '#1b3b70', '#276faf', '#4d9ac7', '#99c8e0', '#d4e6ef',
    '#f8f4f2', '#fbd8c3', '#f2a481', '#d6604d', '#b5202e', '#700c22'
]

THEME_BLUE_RED_PRESERVE_ENDS = [
    '#1b3b70', '#276faf', '#4a6a9a', '#7a78a6', '#a07c93', '#b56e6e',
    '#d6604d', '#b5202e', '#700c22'
]

THEME_PURPLE_BROWN = [
    '#4e659b', '#8a8cbf', '#b8a8cf', '#e7bcc6', '#fdcf9e', '#efa484', '#b6766c'
]

THEMES = {
    'wong': WONG_PALETTE,
    'blue-pink': THEME_BLUE_PINK,
    'blue-red': THEME_BLUE_RED,
    'blue-red-preserve-ends': THEME_BLUE_RED_PRESERVE_ENDS,
    'purple-brown': THEME_PURPLE_BROWN,
}


class NatureViolinPlot:
    """Violin plot generator with Nature Communications styling."""

    def __init__(self):
        self.style = {
            'font.family': 'sans-serif',
            'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
            'font.size': 7,
            'axes.labelsize': 7,
            'axes.titlesize': 7,
            'xtick.labelsize': 7,
            'ytick.labelsize': 7,
            'legend.fontsize': 6.5,
            'axes.linewidth': 0.5 * 0.3528,
            'xtick.major.width': 0.5 * 0.3528,
            'ytick.major.width': 0.5 * 0.3528,
            'xtick.direction': 'out',
            'ytick.direction': 'out',
            'axes.grid': False,
            'figure.facecolor': 'white',
            'axes.facecolor': 'white',
            'pdf.fonttype': 42,
            'svg.fonttype': 'none',
            'text.usetex': False,  # Use mathtext for LaTeX-like rendering (no external LaTeX required)
        }

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data_wide(self, csv_path: str, value_cols: list[str] = None,
                      skiprows: int = 0, delimiter: str = ','):
        """Load data from CSV in wide format (each column is a group).

        Args:
            csv_path:   Path to CSV file.
            value_cols: List of column names to plot as separate violins.
                        If None, auto-selects all numeric columns.
            skiprows:   Rows to skip at start of file.
            delimiter:  CSV delimiter character.

        Returns:
            (df, selected_columns)
        """
        try:
            df = pd.read_csv(csv_path, sep=delimiter, skiprows=skiprows)
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")

        if not value_cols:
            value_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if not value_cols:
                raise ValueError("No numeric columns found in CSV.")
            print(f"Auto-selected {len(value_cols)} numeric columns.")

        # Validate columns
        valid_cols = []
        for col in value_cols:
            if col not in df.columns:
                print(f"Warning: Column '{col}' not found. Skipping.")
                continue
            # Ensure numeric
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].dropna().empty:
                print(f"Warning: Column '{col}' has no valid numeric data. Skipping.")
                continue
            valid_cols.append(col)

        if not valid_cols:
            raise ValueError("No valid numeric data found in selected columns.")

        return df, valid_cols

    # ------------------------------------------------------------------
    # Plot generation
    # ------------------------------------------------------------------

    def generate_violin_plot_wide(
        self,
        df: pd.DataFrame,
        value_cols: list[str],
        x_label: str = '',
        y_label: str = '',
        title: str = '',
        x_label_fontsize: float = 7,
        y_label_fontsize: float = 7,
        title_fontsize: float = 7,
        show_points: bool = True,
        show_points_beside: bool = False,
        show_box: bool = True,
        show_stats: bool = True,
        kde_bandwidth: str = 'scott',
        orientation: str = 'vertical',
        significance_brackets: list[dict] = None,
        theme: str = 'wong',
        fig_width: float = 2.76,
        fig_height: float = 2.76,
        ur_note: str = '',
        ur_note_fontsize: float = 6.5,
        enhance_contrast: bool = False,
    ):
        """Generate violin plot for wide-format data (Origin style)."""
        # Extract data for each column, dropping NaNs individually per column
        group_data = [df[col].dropna().values for col in value_cols]
        group_labels = value_cols

        n_groups = len(group_data)
        base_colors = THEMES.get(theme, WONG_PALETTE)
        
        # Exact-match color interpolation if we have more groups than base colors
        if n_groups <= len(base_colors):
            colors = base_colors[:n_groups]
        else:
            from matplotlib.colors import LinearSegmentedColormap
            cmap = LinearSegmentedColormap.from_list("custom_theme", base_colors)
            colors = [matplotlib.colors.to_hex(cmap(i / (n_groups - 1))) for i in range(n_groups)]

        with plt.rc_context(self.style):
            if orientation == 'horizontal':
                fig, ax = plt.subplots(figsize=(fig_height, fig_width))
            else:
                fig, ax = plt.subplots(figsize=(fig_width, fig_height))

            positions = np.arange(1, n_groups + 1)

            # --- Draw violins (manually to avoid cut-off at min/max) ---
            for i, (pos, data) in enumerate(zip(positions, group_data)):
                if len(data) < 2:
                    continue
                
                # Compute KDE
                try:
                    kde = stats.gaussian_kde(data, bw_method=kde_bandwidth)
                except np.linalg.LinAlgError:
                    continue # Fallback for singular matrix (e.g. all identical values)

                # Extended range for "full" violin (not cut at min/max)
                # Extend by 2 standard deviations or bandwidths
                sd = np.std(data, ddof=1) if len(data) > 1 else 0
                if sd == 0:
                    continue
                bw = kde.factor * sd
                
                eval_min = np.min(data) - 2.5 * bw
                eval_max = np.max(data) + 2.5 * bw
                eval_points = np.linspace(eval_min, eval_max, 200)
                
                density = kde(eval_points)
                # Normalize density to match width=0.6 (so max distance from center is 0.3)
                if density.max() > 0:
                    density = density / density.max() * 0.3
                
                # Enhance contrast logic
                edge_color = colors[i]
                face_alpha = 0.6
                edge_linewidth = 1.0
                
                if enhance_contrast:
                    # Parse color to HSV to check lightness
                    rgb = matplotlib.colors.to_rgb(colors[i])
                    hsv = matplotlib.colors.rgb_to_hsv(rgb)
                    # If lightness (Value) is high and Saturation is low/mid, it's a bright/pale color
                    if hsv[2] > 0.8 and hsv[1] < 0.5:
                        edge_color = '#666666'  # Give pale colors a visible gray outline
                        face_alpha = 0.7        # Make the fill more solid
                        edge_linewidth = 1.2
                
                if orientation == 'vertical':
                    ax.fill_betweenx(eval_points, pos - density, pos + density,
                                     facecolor=colors[i], edgecolor=edge_color,
                                     alpha=face_alpha, linewidth=edge_linewidth)
                else:
                    ax.fill_between(eval_points, pos - density, pos + density,
                                    facecolor=colors[i], edgecolor=edge_color,
                                    alpha=face_alpha, linewidth=edge_linewidth)

            # --- Inner box: median, IQR, whiskers (1.5×IQR) ---
            if show_box:
                for i, (pos, data) in enumerate(zip(positions, group_data)):
                    if len(data) == 0:
                        continue
                    q1, med, q3 = np.percentile(data, [25, 50, 75])
                    iqr = q3 - q1
                    lo_whisk = max(np.min(data), q1 - 1.5 * iqr)
                    hi_whisk = min(np.max(data), q3 + 1.5 * iqr)
                    box_w = 0.08

                    if orientation == 'vertical':
                        # Whisker line
                        ax.plot([pos, pos], [lo_whisk, hi_whisk],
                                color='#333333', linewidth=1.2, zorder=3)
                        # IQR box
                        ax.add_patch(mpatches.FancyBboxPatch(
                            (pos - box_w, q1), 2 * box_w, iqr,
                            boxstyle='square,pad=0', linewidth=1.2,
                            edgecolor='#333333', facecolor='white', zorder=4))
                        # Median line
                        ax.plot([pos - box_w, pos + box_w], [med, med],
                                color='#333333', linewidth=1.8, zorder=5,
                                solid_capstyle='butt')
                    else:
                        ax.plot([lo_whisk, hi_whisk], [pos, pos],
                                color='#333333', linewidth=1.2, zorder=3)
                        ax.add_patch(mpatches.FancyBboxPatch(
                            (q1, pos - box_w), iqr, 2 * box_w,
                            boxstyle='square,pad=0', linewidth=1.2,
                            edgecolor='#333333', facecolor='white', zorder=4))
                        ax.plot([med, med], [pos - box_w, pos + box_w],
                                color='#333333', linewidth=1.8, zorder=5,
                                solid_capstyle='butt')

            # --- Individual data points (jittered) ---
            if show_points:
                rng = np.random.default_rng(42)
                for i, (pos, data) in enumerate(zip(positions, group_data)):
                    if len(data) == 0:
                        continue
                    
                    dot_edge = 'white'
                    dot_alpha = 0.7
                    if enhance_contrast:
                        rgb = matplotlib.colors.to_rgb(colors[i])
                        hsv = matplotlib.colors.rgb_to_hsv(rgb)
                        if hsv[2] > 0.8 and hsv[1] < 0.5:
                            dot_edge = '#666666'
                            dot_alpha = 0.9

                    if show_points_beside:
                        jitter = rng.uniform(0.22, 0.38, size=len(data))
                    else:
                        jitter = rng.uniform(-0.12, 0.12, size=len(data))

                    if orientation == 'vertical':
                        ax.scatter(pos + jitter, data,
                                   s=12, color=colors[i], alpha=dot_alpha,
                                   edgecolors=dot_edge, linewidths=0.5, zorder=6)
                    else:
                        ax.scatter(data, pos + jitter,
                                   s=12, color=colors[i], alpha=dot_alpha,
                                   edgecolors=dot_edge, linewidths=0.5, zorder=6)

            # --- n and median annotations ---
            if show_stats:
                all_valid_data = np.concatenate([d for d in group_data if len(d) > 0])
                val_min = all_valid_data.min()
                val_max = all_valid_data.max()
                val_range = val_max - val_min or 1.0
                offset = val_range * 0.05
                
                for i, (pos, data) in enumerate(zip(positions, group_data)):
                    if len(data) == 0:
                        continue
                    n = len(data)

                    if orientation == 'vertical':
                        ax.text(pos, val_min - offset,
                                f'$n$={n}', ha='center', va='top',
                                fontsize=7, color='#444444')
                    else:
                        ax.text(val_max + offset, pos,
                                f'$n$={n}', ha='left', va='center',
                                fontsize=7, color='#444444')

            # --- Axis ticks and labels ---
            if orientation == 'vertical':
                ax.set_xticks(positions)
                ax.set_xticklabels(group_labels, rotation=0 if n_groups <= 4 else 30,
                                   ha='center' if n_groups <= 4 else 'right')
                if y_label: ax.set_ylabel(y_label, fontsize=y_label_fontsize)
                if x_label: ax.set_xlabel(x_label, fontsize=x_label_fontsize)
            else:
                ax.set_yticks(positions)
                ax.set_yticklabels(group_labels)
                if x_label: ax.set_xlabel(x_label, fontsize=x_label_fontsize)
                if y_label: ax.set_ylabel(y_label, fontsize=y_label_fontsize)

            if title:
                ax.set_title(title, fontsize=title_fontsize, pad=4)

            # Extend x limits a bit so violins don't touch axes
            extra_point_margin = 0.45 if show_points and show_points_beside else 0.0
            ax.set_xlim(positions[0] - 0.7, positions[-1] + 0.7 + extra_point_margin) if orientation == 'vertical' \
                else ax.set_ylim(positions[0] - 0.7, positions[-1] + 0.7 + extra_point_margin)

            # --- Spines ---
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.5 * 0.3528)

            # --- Significance brackets ---
            if significance_brackets:
                all_valid_data = np.concatenate([d for d in group_data if len(d) > 0])
                y_max = all_valid_data.max()
                y_range = all_valid_data.max() - all_valid_data.min()
                
                for bracket in significance_brackets:
                    group1_idx = bracket.get('group1', 0)
                    group2_idx = bracket.get('group2', 1)
                    text = bracket.get('text', '*')
                    y_offset = bracket.get('y_offset', 0.05)  # Fraction of y_range
                    
                    if group1_idx >= n_groups or group2_idx >= n_groups:
                        continue
                    
                    pos1 = positions[group1_idx]
                    pos2 = positions[group2_idx]
                    
                    if orientation == 'vertical':
                        # Calculate bracket height
                        bracket_y = y_max + y_range * y_offset
                        bar_height = y_range * 0.01
                        
                        # Draw horizontal line
                        ax.plot([pos1, pos2], [bracket_y, bracket_y],
                                color='#333333', linewidth=1.0, zorder=10)
                        # Draw left vertical tick
                        ax.plot([pos1, pos1], [bracket_y - bar_height, bracket_y],
                                color='#333333', linewidth=1.0, zorder=10)
                        # Draw right vertical tick
                        ax.plot([pos2, pos2], [bracket_y - bar_height, bracket_y],
                                color='#333333', linewidth=1.0, zorder=10)
                        # Add text
                        ax.text((pos1 + pos2) / 2, bracket_y + y_range * 0.01,
                                text, ha='center', va='bottom', fontsize=8,
                                color='#333333', zorder=10)
                    else:
                        # Horizontal orientation
                        bracket_x = y_max + y_range * y_offset
                        bar_width = y_range * 0.01
                        
                        ax.plot([bracket_x, bracket_x], [pos1, pos2],
                                color='#333333', linewidth=1.0, zorder=10)
                        ax.plot([bracket_x - bar_width, bracket_x], [pos1, pos1],
                                color='#333333', linewidth=1.0, zorder=10)
                        ax.plot([bracket_x - bar_width, bracket_x], [pos2, pos2],
                                color='#333333', linewidth=1.0, zorder=10)
                        ax.text(bracket_x + y_range * 0.01, (pos1 + pos2) / 2,
                                text, ha='left', va='center', fontsize=8,
                                color='#333333', rotation=0, zorder=10)

            # --- Legend / Top Right Note ---
            if ur_note:
                def _parse_latex(s):
                    if not isinstance(s, str): return s
                    return s.replace('$$', '$')
                note_text = _parse_latex(ur_note)
                
                # We place it slightly inside the axes or exactly at the corner
                ax.text(0.98, 0.98, note_text,
                        transform=ax.transAxes, fontsize=ur_note_fontsize,
                        ha='right', va='top',
                        bbox=dict(boxstyle='round,pad=0.3', 
                                 facecolor='white', edgecolor='none', alpha=0.8),
                        zorder=10)

            fig.tight_layout()
            return fig

    # ------------------------------------------------------------------
    # Statistical summary
    # ------------------------------------------------------------------

    def print_summary_wide(self, df: pd.DataFrame, value_cols: list[str]):
        print(f"\nStatistical Summary")
        print("-" * 52)

        for col in value_cols:
            data = df[col].dropna().values
            if len(data) == 0:
                continue
            q1, med, q3 = np.percentile(data, [25, 50, 75])
            print(f"  Column: {col}")
            print(f"    n       = {len(data)}")
            print(f"    Mean    = {np.mean(data):.4f}")
            print(f"    Median  = {med:.4f}")
            print(f"    SD      = {np.std(data, ddof=1):.4f}")
            print(f"    IQR     = {q1:.4f} – {q3:.4f}")
            print(f"    Range   = {np.min(data):.4f} – {np.max(data):.4f}")
            if len(data) <= 5000:
                _, p = stats.shapiro(data)
                print(f"    Shapiro-Wilk p = {p:.4f}"
                      + (" (non-normal *)" if p < 0.05 else ""))
            print()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_figure(self, fig, output_path: str, dpi: int = 1200,
                    fmt: str = None):
        if fmt is None:
            fmt = Path(output_path).suffix.lstrip('.').lower()
        save_kwargs = {'dpi': dpi, 'bbox_inches': 'tight', 'pad_inches': 0.02}
        if fmt == 'tiff':
            save_kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}
        fig.savefig(output_path, format=fmt, **save_kwargs)
        print(f"Figure saved to: {output_path}")
        print(f"Format: {fmt.upper()}, "
              f"DPI: {'vector' if fmt in ('pdf', 'svg', 'eps') else dpi}")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate Nature Communications-compliant violin plots from CSV data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single-group violin (no grouping)
  python violin_plot_generator.py data.csv --value "Response_Time" --output violin.pdf

  # Multi-group violin
  python violin_plot_generator.py data.csv -v "Score" -g "Condition" -o violin.pdf

  # Column indices, horizontal layout, no individual points
  python violin_plot_generator.py data.csv -v 0 -g 1 -o violin.pdf --horizontal --no-points

  # Custom axis labels and title
  python violin_plot_generator.py data.csv -v "D" -g "Group" -o violin.pdf \\
      --ylabel "Diffusion Coeff. (µm²/s)" --title "Cytoplasmic Mobility"

  # High-res PNG
  python violin_plot_generator.py data.csv -v 0 -g 1 -o violin.png --dpi 1200
        """
    )

    parser.add_argument('input', type=str,
                        help='Input CSV file path')
    parser.add_argument('-v', '--value', type=str, default=None,
                        help='Value column name or index (0-based). '
                             'Auto-selects first numeric column if omitted.')
    parser.add_argument('-g', '--group', type=str, default=None,
                        help='Grouping column name or index. '
                             'If omitted, all data forms one violin.')
    parser.add_argument('-o', '--output', type=str, required=True,
                        help='Output file path (e.g., violin.pdf)')
    parser.add_argument('--xlabel', type=str, default='',
                        help='X-axis label override')
    parser.add_argument('--ylabel', type=str, default='',
                        help='Y-axis label override')
    parser.add_argument('--title', type=str, default='',
                        help='Optional plot title')
    parser.add_argument('--dpi', type=int, default=1200,
                        help='DPI for raster formats (default: 1200)')
    parser.add_argument('--format', type=str,
                        choices=['pdf', 'svg', 'eps', 'png', 'tiff'],
                        help='Output format (default: inferred from extension)')
    parser.add_argument('--horizontal', action='store_true',
                        help='Draw violins horizontally')
    parser.add_argument('--no-points', action='store_true',
                        help='Suppress individual data point overlay')
    parser.add_argument('--no-box', action='store_true',
                        help='Suppress inner median / IQR box')
    parser.add_argument('--no-stats', action='store_true',
                        help='Suppress n and median annotations')
    parser.add_argument('--bandwidth', type=str, default='scott',
                        help="KDE bandwidth: 'scott' (default), 'silverman', or a float")
    parser.add_argument('--skiprows', type=int, default=0,
                        help='Rows to skip at start of CSV (default: 0)')
    parser.add_argument('--delimiter', type=str, default=',',
                        help='CSV delimiter (default: comma)')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Convert column args to int if digit string
    value_col = args.value
    if value_col is not None and value_col.isdigit():
        value_col = int(value_col)

    group_col = args.group
    if group_col is not None and group_col.isdigit():
        group_col = int(group_col)

    # Parse bandwidth
    bandwidth = args.bandwidth
    try:
        bandwidth = float(bandwidth)
    except ValueError:
        pass  # keep as string ('scott' / 'silverman')

    try:
        generator = NatureViolinPlot()

        print(f"Reading CSV: {args.input}")
        df, vcol, gcol = generator.load_data(
            args.input,
            value_col=value_col,
            group_col=group_col,
            skiprows=args.skiprows,
            delimiter=args.delimiter,
        )

        generator.print_summary(df, vcol, gcol)

        print("Generating violin plot...")
        fig = generator.generate_violin_plot(
            df, vcol, gcol,
            x_label=args.xlabel,
            y_label=args.ylabel,
            title=args.title,
            show_points=not args.no_points,
            show_box=not args.no_box,
            show_stats=not args.no_stats,
            kde_bandwidth=bandwidth,
            orientation='horizontal' if args.horizontal else 'vertical',
        )

        generator.save_figure(fig, args.output, dpi=args.dpi,
                               fmt=args.format)
        print("\n✓ Violin plot generation complete!")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
