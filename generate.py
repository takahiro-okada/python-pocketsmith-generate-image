"""
PocketSmith CSV/API → note家計簿 自動生成スクリプト
使い方:
  月次CSV: python generate.py data.csv --month 2026-03
  週次CSV: python generate.py data.csv --week --date 2026-04-07
  週次API: python generate.py --api --week --date 2026-04-07
  (引数なし → CSVの最新月を自動取得)
出力: images/ に 日本語・英語の2枚グラフ
"""

import os
import sys
import json
import time
import urllib.error
import urllib.parse
import urllib.request
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

API_BASE_URL = "https://api.pocketsmith.com/v2"

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
TRANSACTION_COLUMNS = [
    "Date",
    "Merchant",
    "Amount",
    "Currency",
    "Transaction Type",
    "Account",
    "Category",
    "Parent Categories",
    "Labels",
    "Memo",
    "Note",
    "ID",
]


def load_dotenv(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def prepare_transactions_dataframe(df):
    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""
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


def load_csv(filepath):
    df = pd.read_csv(filepath)
    return prepare_transactions_dataframe(df)


def _nested_get(data, path, default=""):
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _category_title(transaction):
    category = transaction.get("category")
    if isinstance(category, dict):
        return category.get("title") or category.get("name") or "Uncategorised"
    return (
        transaction.get("category_title")
        or transaction.get("category_name")
        or "Uncategorised"
    )


def _parent_category_title(transaction):
    candidates = [
        ("category", "parent", "title"),
        ("category", "parent", "name"),
        ("category", "parent_category", "title"),
        ("category", "parent_category", "name"),
        ("parent_category", "title"),
        ("parent_category", "name"),
    ]
    for path in candidates:
        value = _nested_get(transaction, path)
        if value:
            return value
    return transaction.get("parent_category_title") or transaction.get("parent_category_name") or ""


def api_transaction_to_row(transaction):
    category = _category_title(transaction)
    account = transaction.get("transaction_account") or transaction.get("account") or {}
    return {
        "Date": transaction.get("date"),
        "Merchant": transaction.get("payee") or transaction.get("merchant") or "",
        "Amount": transaction.get("amount"),
        "Currency": transaction.get("currency_code") or transaction.get("currency") or "",
        "Transaction Type": transaction.get("type") or "",
        "Account": account.get("name", "") if isinstance(account, dict) else "",
        "Category": category,
        "Parent Categories": _parent_category_title(transaction),
        "Labels": transaction.get("labels") or "",
        "Memo": transaction.get("memo") or "",
        "Note": transaction.get("note") or "",
        "ID": transaction.get("id") or "",
    }


def period_range(mode, target=None):
    if mode == "month":
        if target:
            year, month = int(target[:4]), int(target[5:7])
            start = datetime(year, month, 1)
        else:
            today = datetime.today()
            start = datetime(today.year, today.month, 1)

        if start.month == 12:
            next_month = datetime(start.year + 1, 1, 1)
        else:
            next_month = datetime(start.year, start.month + 1, 1)
        end = next_month - timedelta(days=1)
    else:
        base = pd.to_datetime(target).to_pydatetime() if target else datetime.today()
        start = base - timedelta(days=base.weekday())
        end = start + timedelta(days=6)

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_api_transactions(mode, target=None):
    load_dotenv()
    api_key = os.environ.get("POCKETSMITH_API_KEY")
    user_id = os.environ.get("POCKETSMITH_USER_ID")

    missing = [
        name for name, value in {
            "POCKETSMITH_API_KEY": api_key,
            "POCKETSMITH_USER_ID": user_id,
        }.items() if not value
    ]
    if missing:
        raise RuntimeError(
            ".env または環境変数に " + ", ".join(missing) + " を設定してください。"
        )

    start_date, end_date = period_range(mode, target)
    rows = []
    page = 1

    while True:
        params = urllib.parse.urlencode({
            "start_date": start_date,
            "end_date": end_date,
            "type": "debit",
            "page": page,
        })
        url = f"{API_BASE_URL}/users/{user_id}/transactions?{params}"
        request = urllib.request.Request(url, headers={
            "X-Developer-Key": api_key,
            "Accept": "application/json",
            "User-Agent": "pocketsmith-budget-image/1.0",
        })

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                if e.code == 400 and "Requested page is out of bounds" in detail:
                    payload = []
                    break
                raise RuntimeError(
                    f"PocketSmith APIエラー: HTTP {e.code} {e.reason}\n{detail[:500]}"
                ) from e
            except urllib.error.URLError as e:
                if attempt < 2:
                    print(f"  API接続に失敗しました。10秒後に再試行します ({attempt + 1}/3): {e.reason}")
                    time.sleep(10)
                    continue
                raise RuntimeError(f"PocketSmith APIに接続できません: {e.reason}") from e
            except json.JSONDecodeError as e:
                raise RuntimeError("PocketSmith APIのレスポンスをJSONとして読めませんでした。") from e

        if not isinstance(payload, list):
            raise RuntimeError("PocketSmith APIのレスポンス形式が想定外です。")
        if not payload:
            break

        rows.extend(api_transaction_to_row(tx) for tx in payload)
        page += 1

    print(f"  API取得期間: {start_date}〜{end_date}")
    print(f"  API取引件数: {len(rows)}")
    return prepare_transactions_dataframe(pd.DataFrame(rows))


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
    parser.add_argument("csv", nargs="?", help="PocketSmithからエクスポートしたCSVファイル")
    parser.add_argument("--api", action="store_true", help="PocketSmith APIから取引を取得する")
    parser.add_argument("--week",  action="store_true")
    parser.add_argument("--last-week", action="store_true", help="先週分の週次レポートを生成する")
    parser.add_argument("--month", default=None)
    parser.add_argument("--date",  default=None)
    args = parser.parse_args()

    mode   = "week" if args.week else "month"
    target = args.date if args.week else args.month
    if args.last_week:
        if not args.week:
            parser.error("--last-week は --week と一緒に指定してください。")
        target = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        if args.api:
            print("\n🌐 PocketSmith APIから取引を取得...")
            df = fetch_api_transactions(mode, target)
        else:
            if not args.csv:
                parser.error("CSVファイルを指定するか、--api を付けてください。")
            print(f"\n📂 CSV読み込み: {args.csv}")
            df = load_csv(args.csv)

        print(f"📅 期間フィルタ ({mode})...")
        df_p, label_ja, label_en, period_str = filter_period(df, mode, target)

        if df_p.empty:
            print("⚠️  指定期間のデータがありません"); return

        print(f"📈 グラフ生成: {label_ja} / {label_en}")
        path_ja, path_en = make_charts(df_p, label_ja, label_en, period_str)

        print(f"\n✅ 完成！ → images/ を確認してください")
    except RuntimeError as e:
        print(f"\n❌ エラー: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"   日本語グラフ : {path_ja}")
    print(f"   英語グラフ   : {path_en}")


if __name__ == "__main__":
    main()
