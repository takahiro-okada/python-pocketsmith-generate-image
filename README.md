# PocketSmith Budget Visualizer

A Python script that automatically generates household budget charts from [PocketSmith](https://www.pocketsmith.com/) CSV exports — in both **Japanese and English** — for publishing on note or any blog platform.

---

## 📸 Sample Output

Charts are exported as PNG images in both languages.

| Japanese | English |
|----------|---------|
| `chart_2026-03_ja.png` | `chart_2026-03_en.png` |

Each chart includes:
- **Pie chart** — spending breakdown by parent category
- **Horizontal bar chart** — spending breakdown by subcategory

---

## 🗂 Project Structure

```
.
├── generate.py       # Main script
├── data.csv          # PocketSmith export (excluded from git)
├── README.md
└── images/           # Generated chart images (auto-created)
    ├── chart_2026-03_ja.png
    ├── chart_2026-03_en.png
    └── ...
```

---

## ⚙️ Requirements

- Python 3.8+
- pandas
- matplotlib

### Setup (recommended: virtual environment)

Using a virtual environment avoids conflicts with system-managed Python (e.g. Homebrew on macOS).

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate it
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install pandas matplotlib
```

From the next session onwards, just run `source venv/bin/activate` before using the script.

> **Japanese font**: On macOS, `Hiragino Sans` is used automatically. On Windows, `Meiryo` or `Yu Gothic` is used. On Linux, `Noto Sans CJK JP` or `IPAGothic` is used. The script will print which font was detected when you run it.

---

## 🚀 Usage

### 1. Export CSV from PocketSmith

Go to **Reports → Transaction Search → Export CSV** and save the file as `data.csv` in the project folder.

### 2. Activate the virtual environment

```bash
source venv/bin/activate
```

### 3. Run the script

**Monthly report:**
```bash
python generate.py data.csv --month 2026-03
```

**Weekly report** (week containing the given date):
```bash
python generate.py data.csv --week --date 2026-04-07
```

**Auto-detect latest month** (no arguments needed):
```bash
python generate.py data.csv
```

### 4. Find your images

Generated PNG files will be saved in the `images/` folder.

---

## 🏷 Category Structure

The script maps PocketSmith categories as follows:

| Subcategory | Parent Category |
|---|---|
| Housing & Utilities | Fixed |
| Communication | Fixed |
| Groceries | Food |
| Dining Out | Food |
| Daily Necessities | Daily Necessities |
| Car Expenses | Transport |
| Bus / Others | Transport |
| Leisure | Leisure |
| Education | Education |

To customize categories, edit the `CATEGORY_MAP`, `JP_PARENT`, and `JP_SUB` dictionaries at the top of `generate.py`.

---

## 📝 Notes

- Transactions categorized as `Transfer from Japn` are excluded from charts (treated as income, not expenses).
- Only **debit** transactions are included.
- CSV export is available on the **free PocketSmith plan** and above.
- Add `data.csv` and `venv/` to your `.gitignore` to avoid accidentally committing personal data.

---

## 🔮 Future Plans

- [ ] Automate CSV export via PocketSmith API (requires paid plan)
- [ ] Auto-publish charts to note via API
- [ ] Add monthly trend comparison charts

---

## 👤 Author

Living in New Zealand 🇳🇿 | Sharing weekly & monthly budgets on [note](https://note.com)