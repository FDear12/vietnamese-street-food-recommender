"""
visualize_data.py
─────────────────
Đọc metadata.json từ step1_crawl → vẽ 3 biểu đồ:
  1. Heatmap: Món × Thành phố (số video)
  2. Bar chart tổng hợp: Tổng video theo Món (tất cả location)
  3. Stacked bar: Món × Thành phố (màu phân lớp)

Lưu ra:
  - chart_heatmap.png
  - chart_by_mon.png
  - chart_stacked.png
  - chart_all.png  (4 biểu đồ ghép 1 file)

Chạy: python visualize_data.py [đường_dẫn_metadata.json]
Mặc định: ./metadata.json
"""

import json
import sys
import os
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-GUI backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ─── CONFIG từ config.py (copy nhanh để standalone) ───
HASHTAG_CHINH = {
    "banhbeo"       : "Bánh Bèo",
    "banhbotloc"    : "Bánh Bột Lọc",
    "banhcan"       : "Bánh Căn",
    "banhcanh"      : "Bánh Canh",
    "banhbao"       : "Bánh Bao",
    "banhcuon"      : "Bánh Cuốn",
    "banhkhot"      : "Bánh Khọt",
    
    "banhtrangnuong": "Bánh Tráng Nướng",
    "banhxeo"       : "Bánh Xèo",
    "bunbohue"      : "Bún Bò Huế",
    "buncha"        : "Bún Chả",
    "bundaumamtom"  : "Bún Đậu Mắm Tôm",
    "bunmam"        : "Bún Mắm",
    "bunrieu"       : "Bún Riêu",
    "bunthitnuong"  : "Bún Thịt Nướng",
    "caolau"        : "Cao Lầu",
    "chaolong"      : "Cháo Lòng",
    "comtam"        : "Cơm Tấm",
    
    "hutieu"        : "Hủ Tiếu",
    "nemchua"       : "Nem Chua",
    "pho"           : "Phở",
    
    "miquang"       : "Mì Quảng",
}

LOCATIONS_ORDER = ["Đà Nẵng", "Hồ Chí Minh", "Hà Nội", "Toàn quốc"]

# ─── PALETTE ──────────────────────────────────────────
PALETTE = {
    "Đà Nẵng"     : "#FF6B6B",
    "Hồ Chí Minh" : "#FFA94D",
    "Hà Nội"      : "#51CF66",
    "Toàn quốc"   : "#74C0FC",
}
BG_COLOR   = "#0F1117"
TEXT_COLOR = "#E8E8E8"
GRID_COLOR = "#2A2A3A"
ACCENT     = "#FFD43B"

# ─── LOAD DATA ────────────────────────────────────────

def load_meta(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ Đã load {len(data)} records từ {path}")
    return data


def build_matrix(data: list[dict]):
    """Trả về dict[mon_label][location_label] = count"""
    matrix = defaultdict(lambda: defaultdict(int))
    
    loc_map = {
        "Đà Nẵng"     : "Đà Nẵng",
        "Hồ Chí Minh" : "Hồ Chí Minh",
        "Hà Nội"      : "Hà Nội",
        "Toàn quốc"   : "Toàn quốc",
    }
    
    for r in data:
        hashtag  = r.get("hashtag_chinh", "")
        location = r.get("location_search", "")
        mon_label = HASHTAG_CHINH.get(hashtag, hashtag)
        loc_label = loc_map.get(location, location)
        matrix[mon_label][loc_label] += 1
    
    return matrix


# ─── STYLE HELPER ─────────────────────────────────────

def apply_dark(fig, axes):
    fig.patch.set_facecolor(BG_COLOR)
    for ax in (axes if hasattr(axes, "__iter__") else [axes]):
        ax.set_facecolor(BG_COLOR)
        ax.tick_params(colors=TEXT_COLOR, labelsize=8)
        ax.xaxis.label.set_color(TEXT_COLOR)
        ax.yaxis.label.set_color(TEXT_COLOR)
        ax.title.set_color(ACCENT)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID_COLOR)
        ax.grid(color=GRID_COLOR, linewidth=0.5, linestyle="--", alpha=0.6)


# ─── CHART 1: HEATMAP ─────────────────────────────────

def plot_heatmap(matrix: dict, out_path: str):
    mons  = [HASHTAG_CHINH[k] for k in HASHTAG_CHINH]   # thứ tự từ config
    locs  = LOCATIONS_ORDER
    
    arr = np.zeros((len(mons), len(locs)), dtype=int)
    for i, mon in enumerate(mons):
        for j, loc in enumerate(locs):
            arr[i, j] = matrix[mon][loc]

    fig, ax = plt.subplots(figsize=(10, 10))
    apply_dark(fig, ax)

    cmap = plt.cm.YlOrRd
    im = ax.imshow(arr, cmap=cmap, aspect="auto", vmin=0)

    ax.set_xticks(range(len(locs)))
    ax.set_xticklabels(locs, fontsize=10, color=TEXT_COLOR)
    ax.set_yticks(range(len(mons)))
    ax.set_yticklabels(mons, fontsize=9, color=TEXT_COLOR)

    # Ghi số vào ô
    for i in range(len(mons)):
        for j in range(len(locs)):
            val = arr[i, j]
            color = "white" if val > arr.max() * 0.5 else "#CCCCCC"
            ax.text(j, i, str(val), ha="center", va="center",
                    fontsize=8, color=color, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors=TEXT_COLOR)
    cbar.set_label("Số video", color=TEXT_COLOR, fontsize=9)

    ax.set_title("🗺️  Heatmap: Món × Thành phố", fontsize=13,
                 color=ACCENT, fontweight="bold", pad=14)
    ax.grid(False)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  💾 {out_path}")


# ─── CHART 2: BAR TỔNG HỢP THEO MÓN ──────────────────

def plot_by_mon(matrix: dict, out_path: str):
    mons   = [HASHTAG_CHINH[k] for k in HASHTAG_CHINH]
    totals = [sum(matrix[m][l] for l in LOCATIONS_ORDER) for m in mons]

    # Sắp xếp descending
    pairs  = sorted(zip(totals, mons), reverse=True)
    totals, mons = zip(*pairs) if pairs else ([], [])

    fig, ax = plt.subplots(figsize=(12, 7))
    apply_dark(fig, ax)

    colors = plt.cm.plasma(np.linspace(0.2, 0.85, len(mons)))
    bars = ax.barh(mons, totals, color=colors, height=0.65, edgecolor=BG_COLOR, linewidth=0.8)

    # Ghi số bên phải bar
    for bar, val in zip(bars, totals):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", ha="left", color=TEXT_COLOR, fontsize=8.5)

    ax.set_xlabel("Tổng số video", color=TEXT_COLOR, fontsize=10)
    ax.set_title("📊  Tổng video theo Món (tất cả thành phố)", fontsize=13,
                 color=ACCENT, fontweight="bold", pad=14)
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  💾 {out_path}")


# ─── CHART 3: STACKED BAR MÓN × THÀNH PHỐ ────────────

def plot_stacked(matrix: dict, out_path: str):
    mons  = [HASHTAG_CHINH[k] for k in HASHTAG_CHINH]
    locs  = LOCATIONS_ORDER

    # Sắp xếp theo tổng
    totals_map = {m: sum(matrix[m][l] for l in locs) for m in mons}
    mons = sorted(mons, key=lambda m: totals_map[m], reverse=True)

    arr = {loc: [matrix[m][loc] for m in mons] for loc in locs}

    fig, ax = plt.subplots(figsize=(13, 8))
    apply_dark(fig, ax)

    x = np.arange(len(mons))
    bottom = np.zeros(len(mons))

    for loc in locs:
        vals = np.array(arr[loc])
        bars = ax.bar(x, vals, bottom=bottom, label=loc,
                      color=PALETTE[loc], edgecolor=BG_COLOR,
                      linewidth=0.5, width=0.7, alpha=0.9)
        # Ghi số trong segment nếu đủ to
        for i, (bar, val) in enumerate(zip(bars, vals)):
            if val >= 3:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bottom[i] + val / 2,
                        str(val), ha="center", va="center",
                        color="white", fontsize=7, fontweight="bold")
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(mons, rotation=45, ha="right", fontsize=8, color=TEXT_COLOR)
    ax.set_ylabel("Số video", color=TEXT_COLOR, fontsize=10)
    ax.set_title("🏙️  Video theo Món & Thành phố (stacked)", fontsize=13,
                 color=ACCENT, fontweight="bold", pad=14)

    legend = ax.legend(loc="upper right", framealpha=0.25, labelcolor=TEXT_COLOR,
                       facecolor=BG_COLOR, edgecolor=GRID_COLOR, fontsize=9)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  💾 {out_path}")


# ─── CHART 4: PIE LOCATION ────────────────────────────

def plot_pie_location(matrix: dict, out_path: str):
    locs   = LOCATIONS_ORDER
    totals = []
    for loc in locs:
        t = sum(matrix[m][loc] for m in HASHTAG_CHINH.values())
        totals.append(t)

    colors = [PALETTE[l] for l in locs]
    labels = [f"{l}\n({t})" for l, t in zip(locs, totals)]

    fig, ax = plt.subplots(figsize=(7, 7))
    apply_dark(fig, ax)
    ax.set_facecolor(BG_COLOR)

    wedges, texts, autotexts = ax.pie(
        totals, labels=labels, colors=colors,
        autopct="%1.1f%%", startangle=140,
        pctdistance=0.75, labeldistance=1.12,
        wedgeprops=dict(edgecolor=BG_COLOR, linewidth=2),
    )
    for t in texts:
        t.set_color(TEXT_COLOR)
        t.set_fontsize(9)
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
        at.set_fontweight("bold")

    ax.set_title("🌏  Phân bổ video theo Thành phố", fontsize=13,
                 color=ACCENT, fontweight="bold", pad=14)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  💾 {out_path}")


# ─── CHART GHÉP ALL ───────────────────────────────────

def plot_all(matrix: dict, out_path: str):
    """Ghép 4 chart vào 1 file duy nhất (2×2)."""
    mons  = [HASHTAG_CHINH[k] for k in HASHTAG_CHINH]
    locs  = LOCATIONS_ORDER

    arr_hm = np.zeros((len(mons), len(locs)), dtype=int)
    for i, mon in enumerate(mons):
        for j, loc in enumerate(locs):
            arr_hm[i, j] = matrix[mon][loc]

    totals_by_mon = [sum(matrix[m][l] for l in locs) for m in mons]
    pairs         = sorted(zip(totals_by_mon, mons), reverse=True)
    totals_s, mons_s = zip(*pairs) if pairs else ([], [])

    mons_stacked = sorted(mons, key=lambda m: sum(matrix[m][l] for l in locs), reverse=True)
    arr_st = {loc: [matrix[m][loc] for m in mons_stacked] for loc in locs}

    totals_loc = [sum(matrix[m][loc] for m in HASHTAG_CHINH.values()) for loc in locs]

    fig = plt.figure(figsize=(22, 18))
    fig.patch.set_facecolor(BG_COLOR)

    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.32,
                          left=0.06, right=0.97, top=0.93, bottom=0.06)

    # ── Heatmap ──────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(BG_COLOR)
    im = ax1.imshow(arr_hm, cmap=plt.cm.YlOrRd, aspect="auto", vmin=0)
    ax1.set_xticks(range(len(locs)));  ax1.set_xticklabels(locs, fontsize=9, color=TEXT_COLOR)
    ax1.set_yticks(range(len(mons)));  ax1.set_yticklabels(mons, fontsize=7.5, color=TEXT_COLOR)
    for i in range(len(mons)):
        for j in range(len(locs)):
            v = arr_hm[i, j]
            c = "white" if v > arr_hm.max() * 0.5 else "#BBBBBB"
            ax1.text(j, i, str(v), ha="center", va="center", fontsize=7, color=c, fontweight="bold")
    cb = fig.colorbar(im, ax=ax1, fraction=0.03, pad=0.02)
    cb.ax.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax1.set_title("Heatmap: Món × Thành phố", color=ACCENT, fontsize=11, fontweight="bold", pad=10)
    ax1.tick_params(colors=TEXT_COLOR)
    for sp in ax1.spines.values(): sp.set_edgecolor(GRID_COLOR)
    ax1.grid(False)

    # ── Bar tổng hợp theo Món ────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(BG_COLOR)
    colors_b = plt.cm.plasma(np.linspace(0.2, 0.85, len(mons_s)))
    bars = ax2.barh(mons_s, totals_s, color=colors_b, height=0.65, edgecolor=BG_COLOR, linewidth=0.6)
    for bar, val in zip(bars, totals_s):
        ax2.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                 str(val), va="center", ha="left", color=TEXT_COLOR, fontsize=7.5)
    ax2.invert_yaxis()
    ax2.set_xlabel("Số video", color=TEXT_COLOR, fontsize=9)
    ax2.set_title("Tổng video theo Món", color=ACCENT, fontsize=11, fontweight="bold", pad=10)
    ax2.tick_params(colors=TEXT_COLOR, labelsize=8)
    ax2.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax2.grid(color=GRID_COLOR, linewidth=0.4, linestyle="--", axis="x", alpha=0.5)
    for sp in ax2.spines.values(): sp.set_edgecolor(GRID_COLOR)

    # ── Stacked bar ──────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor(BG_COLOR)
    x      = np.arange(len(mons_stacked))
    bottom = np.zeros(len(mons_stacked))
    for loc in locs:
        vals = np.array(arr_st[loc])
        bars3 = ax3.bar(x, vals, bottom=bottom, label=loc,
                        color=PALETTE[loc], edgecolor=BG_COLOR, linewidth=0.4,
                        width=0.72, alpha=0.92)
        for i, (b3, val) in enumerate(zip(bars3, vals)):
            if val >= 3:
                ax3.text(b3.get_x() + b3.get_width() / 2, bottom[i] + val / 2,
                         str(val), ha="center", va="center", color="white",
                         fontsize=6.5, fontweight="bold")
        bottom += vals
    ax3.set_xticks(x)
    ax3.set_xticklabels(mons_stacked, rotation=45, ha="right", fontsize=7, color=TEXT_COLOR)
    ax3.set_ylabel("Số video", color=TEXT_COLOR, fontsize=9)
    ax3.set_title("Video theo Món & Thành phố (stacked)", color=ACCENT, fontsize=11, fontweight="bold", pad=10)
    ax3.legend(loc="upper right", framealpha=0.25, labelcolor=TEXT_COLOR,
               facecolor=BG_COLOR, edgecolor=GRID_COLOR, fontsize=8)
    ax3.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax3.grid(color=GRID_COLOR, linewidth=0.4, linestyle="--", axis="y", alpha=0.5)
    for sp in ax3.spines.values(): sp.set_edgecolor(GRID_COLOR)

    # ── Pie phân bổ thành phố ────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(BG_COLOR)
    colors_p = [PALETTE[l] for l in locs]
    labels_p = [f"{l}\n({t})" for l, t in zip(locs, totals_loc)]
    wedges, texts, autotexts = ax4.pie(
        totals_loc, labels=labels_p, colors=colors_p,
        autopct="%1.1f%%", startangle=140, pctdistance=0.75,
        labeldistance=1.12, wedgeprops=dict(edgecolor=BG_COLOR, linewidth=2),
    )
    for t in texts:
        t.set_color(TEXT_COLOR); t.set_fontsize(9)
    for at in autotexts:
        at.set_color("white"); at.set_fontsize(8); at.set_fontweight("bold")
    ax4.set_title("Phân bổ video theo Thành phố", color=ACCENT, fontsize=11, fontweight="bold", pad=10)

    # ── Tiêu đề chính ────────────────────────────────
    fig.suptitle("TikTok Food Crawler — Phân tích dữ liệu thô (metadata.json)",
                 fontsize=15, color=ACCENT, fontweight="bold", y=0.97)

    fig.savefig(out_path, dpi=150, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  💾 {out_path}")


# ─── PRINT SUMMARY TABLE ──────────────────────────────

def print_summary(matrix: dict, data: list):
    locs  = LOCATIONS_ORDER
    mons  = list(HASHTAG_CHINH.values())

    print("\n" + "="*65)
    print("📊 THỐNG KÊ TỔNG HỢP")
    print("="*65)

    # Tổng theo location
    print("\n📍 Theo Thành phố:")
    for loc in locs:
        t = sum(matrix[m][loc] for m in mons)
        bar = "█" * min(t, 50)
        print(f"  {loc:<16} {t:>4}  {bar}")

    # Tổng theo món (top 10)
    print("\n🍜 Top 10 Món:")
    totals = [(sum(matrix[m][l] for l in locs), m) for m in mons]
    for t, m in sorted(totals, reverse=True)[:10]:
        bar = "█" * min(t, 40)
        print(f"  {m:<22} {t:>4}  {bar}")

    # Tổng chung
    total_all  = len(data)
    total_duyet = sum(1 for r in data if r.get("duyet"))
    print(f"\n  Tổng video crawled : {total_all}")
    print(f"  Đã duyệt (≤30 ngày): {total_duyet} ({total_duyet/total_all*100:.1f}%)" if total_all else "")
    print("="*65 + "\n")


# ─── MAIN ─────────────────────────────────────────────

def main():
    meta_path = sys.argv[1] if len(sys.argv) > 1 else "metadata.json"

    if not os.path.exists(meta_path):
        print(f"❌ Không tìm thấy: {meta_path}")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  TikTok Food Crawler — Visualize Raw Data")
    print(f"{'='*50}\n")

    try:
        import matplotlib
        print(f"✅ matplotlib {matplotlib.__version__}")
    except ImportError:
        print("❌ Thiếu matplotlib. Cài: pip install matplotlib numpy")
        sys.exit(1)

    data   = load_meta(meta_path)
    matrix = build_matrix(data)
    print_summary(matrix, data)

    out_dir = Path(meta_path).parent
    print("🎨 Đang vẽ biểu đồ...\n")

    plot_heatmap  (matrix, str(out_dir / "chart_heatmap.png"))
    plot_by_mon   (matrix, str(out_dir / "chart_by_mon.png"))
    plot_stacked  (matrix, str(out_dir / "chart_stacked.png"))
    plot_pie_location(matrix, str(out_dir / "chart_pie_location.png"))
    plot_all      (matrix, str(out_dir / "chart_all.png"))

    print(f"""
✅ Xong! Các file ảnh:
   • chart_heatmap.png        — Heatmap Món × Thành phố
   • chart_by_mon.png         — Bar tổng video theo Món
   • chart_stacked.png        — Stacked bar Món × Thành phố  
   • chart_pie_location.png   — Pie phân bổ Thành phố
   • chart_all.png            — Tất cả ghép 1 file (chia sẻ nhanh)
""")


if __name__ == "__main__":
    main()
