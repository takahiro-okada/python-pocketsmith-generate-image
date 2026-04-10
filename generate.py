"""
PocketSmith CSV → note家計簿 自動生成スクリプト
使い方:
  月次: python pocketsmith_to_note.py generate.csv --month 2026-03
  週次: python pocketsmith_to_note.py generate.csv --week --date 2026-04-07
  (引数なし → CSVの最新月を自動取得)
出力: note_output/ に 日本語・英語の2枚グラフ + note下書きMarkdown
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
from pathlib import Path
import argparse
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ========== フォント ==========
# Mac / Windows / Linux の順で日本語フォントを自動検出
JP_FONT_CANDIDATES = [
    "Hiragino Sans",             # Mac
    "Hiragino Maru Gothic Pro",  # Mac (fallback)
    "Yu Gothic",                 # Windows
    "Meiryo",                    # Windows (fallback)
    "Noto Sans CJK JP",          # Linux
    "IPAGothic",                 # Linux (fallback)
]

JP_FONT = None
available = {f.name for f in fm.fontManager.ttflist}
for fname in JP_FONT_CANDIDATES:
    if fname in available:
        JP_FONT = fname
        break

if JP_FONT:
    print(f"  フォント: {JP_FONT}")
else:
    print("  ⚠️  日本語フォントが見つかりません。日本語版は文字化けする可能性があります。")

def set_font(lang):
    if lang == "ja" and JP_FONT:
        plt.rcParams["font.family"] = JP_FONT
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

# ========== カテゴリ設定 ==========
CATEGORY_MAP = {
    "Housing & Utilities": "Fixed",
    "Communication":       "Fixed",
    "Groceries":           "Food",
    "Dining Out":          "Food",
    "Daily Necessities":   "Daily Necessities",
    "Car Expenses":        "Transport",
    "Bus / Others":        "Transport",
    "Transport":           "Transport",
    "Leisure":             "Leisure",
    "Education":           "Education",
    "Special":             "Special",
}

# 日本語ラベル
JP_PARENT = {
    "Fixed":             "固定費",
    "Food":              "食費",
    "Daily Necessities": "日用品",
    "Transport":         "交通費",
    "Leisure":           "娯楽",
    "Education":         "教育",
    "Special":           "その他",
}
JP_SUB = {
    "Housing & Utilities": "住居・光熱費",
    "Communication":       "通信費",
    "Groceries":           "食料品",
    "Dining Out":          "外食",
    "Car Expenses":        "車関連",
    "Bus / Others":        "バス・その他",
    "Transport":           "交通費",
    "Daily Necessities":   "日用品",
    "Leisure":             "娯楽",
    "Education":           "教育",
    "Special":             "その他",
}

PARENT_COLORS = {
    "Fixed":             "#4E7AC7",
    "Food":              "#E07B54",
    "Daily Necessities": "#6BBF8E",
    "Transport":         "#F5C842",
    "Leisure":           "#B57BCC",
    "Education":         "#4BBFBF",
    "Special":           "#C0C0C0",
}
SUB_COLORS = {
    "Housing & Utilities": "#7FA8E0",
    "Communication":       "#A3C0F0",
    "Groceries":           "#F0A87A",
    "Dining Out":          "#F5C9A8",
    "Car Expenses":        "#FFE066",
    "Bus / Others":        "#FFD700",
    "Transport":           "#E8C53A",
    "Daily Necessities":   "#6BBF8E",
    "Leisure":             "#B57BCC",
    "Education":           "#4BBFBF",
    "Special":             "#C0C0C0",
}

EXCLUDE_CATEGORIES = {"Transfer from Japn"}
OUTPUT_DIR = Path("images")


def load_csv(filepath):
    df = pd.read_csv(filepath)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df = df[df["Amount"] < 0].copy()
    df = df[~df["Category"].isin(EXCLUDE_CATEGORIES)].copy()
    df["Amount_abs"] = df["Amount"].abs()
    df["Parent"] = df.apply(
        lambda r: r["Parent Categories"]
        if pd.notna(r["Parent Categories"]) and str(r["Parent Categories"]).strip()
        else CATEGORY_MAP.get(r["Category"], r["Category"]),
        axis=1
    )
    return df


def filter_period(df, mode, target=None):
    if mode == "month":
        if target:
            year, month = int(target[:4]), int(target[5:7])
        else:
            latest = df["Date"].max()
            year, month = latest.year, latest.month
        mask = (df["Date"].dt.year == year) & (df["Date"].dt.month == month)
        label_ja = f"{year}年{month}月"
        label_en = f"{datetime(year, month, 1).strftime('%B %Y')}"
        period_str = f"{year}-{month:02d}"
    else:
        base = pd.to_datetime(target) if target else df["Date"].max()
        week_start = base - timedelta(days=base.weekday())
        week_end = week_start + timedelta(days=6)
        mask = (df["Date"] >= week_start) & (df["Date"] <= week_end)
        label_ja = f"{week_start.strftime('%m/%d')}〜{week_end.strftime('%m/%d')}"
        label_en = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        period_str = week_start.strftime("%Y-W%W")
    return df[mask].copy(), label_ja, label_en, period_str


def _draw_chart(df, title, period_str, parent_sum, sub_sum, total, lang):
    """lang='ja' or 'en' で1枚作成して保存、パスを返す"""
    set_font(lang)

    def pname(k): return JP_PARENT.get(k, k) if lang == "ja" else k
    def sname(k): return JP_SUB.get(k, k)    if lang == "ja" else k

    fig = plt.figure(figsize=(12, 6), facecolor="#FAFAF8")
    gs = GridSpec(1, 2, figure=fig, wspace=0.38)
    ax_pie = fig.add_subplot(gs[0, 0])
    ax_bar = fig.add_subplot(gs[0, 1])

    # 円グラフ
    pie_labels = parent_sum.index.tolist()
    pie_values = parent_sum.values
    pie_colors = [PARENT_COLORS.get(p, "#AAAAAA") for p in pie_labels]
    _, _, autotexts = ax_pie.pie(
        pie_values, colors=pie_colors,
        autopct=lambda p: f"{p:.1f}%",
        startangle=140,
        wedgeprops=dict(linewidth=1.5, edgecolor="white"),
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_fontsize(8); at.set_color("white"); at.set_fontweight("bold")

    legend_handles = [
        mpatches.Patch(color=PARENT_COLORS.get(p, "#AAA"),
                       label=f"{pname(p)}  ${v:.0f}")
        for p, v in zip(pie_labels, pie_values)
    ]
    ax_pie.legend(handles=legend_handles, loc="lower left",
                  bbox_to_anchor=(-0.2, -0.38), fontsize=8, frameon=False)

    pie_title = "カテゴリ別内訳" if lang == "ja" else "Category Breakdown"
    ax_pie.set_title(f"{pie_title}\n合計: NZD ${total:.0f}" if lang == "ja"
                     else f"{pie_title}\nTotal: NZD ${total:.0f}",
                     fontsize=11, pad=12, fontweight="bold", color="#333")

    # 横棒グラフ
    sub_cats  = [sname(c) for c in sub_sum.index.tolist()]
    sub_vals  = sub_sum.values
    sub_c     = [SUB_COLORS.get(c, "#AAAAAA") for c in sub_sum.index.tolist()]
    bars = ax_bar.barh(sub_cats[::-1], sub_vals[::-1], color=sub_c[::-1],
                       edgecolor="white", linewidth=0.8, height=0.6)
    for bar, val in zip(bars, sub_vals[::-1]):
        ax_bar.text(bar.get_width() + total * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"${val:.0f}", va="center", ha="left", fontsize=8, color="#555")
    ax_bar.set_xlim(0, total * 1.3)
    ax_bar.set_xlabel("NZD ($)", fontsize=9, color="#555")
    bar_title = "サブカテゴリ別支出" if lang == "ja" else "Subcategory Breakdown"
    ax_bar.set_title(bar_title, fontsize=11, pad=12, fontweight="bold", color="#333")
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.tick_params(axis="y", labelsize=8)
    ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}"))

    main_title = f"家計簿 | {title}" if lang == "ja" else f"Household Budget | {title}"
    fig.suptitle(main_title, fontsize=15, fontweight="bold", color="#222", y=1.02)

    path = OUTPUT_DIR / f"chart_{period_str}_{lang}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="#FAFAF8")
    plt.close(fig)
    print(f"  グラフ保存 ({lang}): {path}")
    return path


def make_charts(df, label_ja, label_en, period_str):
    OUTPUT_DIR.mkdir(exist_ok=True)
    parent_sum = df.groupby("Parent")["Amount_abs"].sum().sort_values(ascending=False)
    sub_sum    = df.groupby("Category")["Amount_abs"].sum().sort_values(ascending=False)
    total      = df["Amount_abs"].sum()

    path_ja = _draw_chart(df, label_ja, period_str, parent_sum, sub_sum, total, "ja")
    path_en = _draw_chart(df, label_en, period_str, parent_sum, sub_sum, total, "en")
    return path_ja, path_en



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--week",  action="store_true")
    parser.add_argument("--month", default=None)
    parser.add_argument("--date",  default=None)
    args = parser.parse_args()

    mode   = "week" if args.week else "month"
    target = args.date if args.week else args.month

    print(f"\n📂 CSV読み込み: {args.csv}")
    df = load_csv(args.csv)

    print(f"📅 期間フィルタ ({mode})...")
    df_p, label_ja, label_en, period_str = filter_period(df, mode, target)

    if df_p.empty:
        print("⚠️  指定期間のデータがありません"); return

    print(f"📈 グラフ生成: {label_ja} / {label_en}")
    path_ja, path_en = make_charts(df_p, label_ja, label_en, period_str)

    print(f"\n✅ 完成！ → images/ を確認してください")
    print(f"   日本語グラフ : {path_ja}")
    print(f"   英語グラフ   : {path_en}")


if __name__ == "__main__":
    main()