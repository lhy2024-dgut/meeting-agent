"""远场 vs 近场 ASR 对比图表生成器

生成对比图表：
  1. far_cer_by_meeting.png   — 远场每场会议 CER 条形图
  2. near_vs_far_cer.png      — 近场 vs 远场 CER 对比图
  3. far_cer_vs_near_cer.png  — 远场/近场 CER 相关性散点图

用法：
  cd evaluation && python plot_far_comparison.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── 路径 ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
NEAR_PATH = BASE_DIR / "asr_eval_results_near.json"
FAR_PATH = BASE_DIR / "asr_eval_results_far.json"
OUT_DIR = BASE_DIR

# ── 中文字体注册 ──────────────────────────────────────────────
_CN_FONT = None
_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "DengXian",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
]
for name in _CANDIDATES:
    try:
        plt.rcParams["font.family"] = name
        fig_test, ax_test = plt.subplots(figsize=(1, 0.5))
        ax_test.set_title("测试")
        fig_test.savefig(Path.home() / "_font_test.png", dpi=50)
        plt.close(fig_test)
        _CN_FONT = name
        break
    except Exception:
        continue

if _CN_FONT is None:
    print("[WARN] 无中文字体，改用 sans-serif")
    plt.rcParams["font.family"] = "sans-serif"
else:
    plt.rcParams["font.family"] = _CN_FONT
    plt.rcParams["axes.unicode_minus"] = False

# ── 颜色 ──────────────────────────────────────────────────────
NEAR_COLOR = "#4A90D9"    # 近场蓝色
FAR_COLOR = "#E8833A"     # 远场橙色
GREEN = "#2ECC71"
YELLOW = "#F1C40F"
RED = "#E74C3C"


def load_results(path: Path) -> dict | None:
    if not path.exists():
        print(f"  [SKIP] {path.name} 不存在")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ================================================================
# 1. 远场每场会议 CER 条形图
# ================================================================
def plot_far_cer_by_meeting(far_data: dict):
    print("\n[1] 远场每场会议 CER 条形图...")

    results = far_data.get("results", [])
    if not results:
        print("  [SKIP] 无数据")
        return

    # 排序
    results_sorted = sorted(results, key=lambda r: r["cer"])

    meetings = [r["name"] for r in results_sorted]
    cers = [r["cer"] * 100 for r in results_sorted]  # → %
    durations = [r.get("duration_min", 0) for r in results_sorted]

    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars = ax.barh(meetings, cers, color=FAR_COLOR, edgecolor="white", height=0.65)

    # 颜色标注区间
    for bar, cer_val in zip(bars, cers):
        if cer_val < 40:
            bar.set_color(GREEN)
        elif cer_val < 60:
            bar.set_color(YELLOW)
        else:
            bar.set_color(RED)

    # 标注数值和时长
    for bar, cer_val, dur in zip(bars, cers, durations):
        ax.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{cer_val:.1f}%  ({dur:.0f}min)",
            va="center",
            fontsize=9,
        )

    ax.set_xlabel("CER (%)", fontsize=11)
    ax.set_title("AliMeeting 远场 ASR — 每场会议 CER", fontsize=13, fontweight="bold")
    ax.set_xlim(0, max(cers) * 1.25)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=GREEN, label="[OK] 良好 (< 40%)"),
        Patch(facecolor=YELLOW, label="[WARN] 一般 (40-60%)"),
        Patch(facecolor=RED, label="[X] 较差 (> 60%)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    # 添加平均线
    avg_cer = far_data.get("avg_cer", 0) * 100
    ax.axvline(avg_cer, color="red", linestyle="--", linewidth=1.5, alpha=0.7)
    ax.text(avg_cer + 0.5, -0.4, f"平均 {avg_cer:.1f}%", fontsize=9, color="red")

    fig.tight_layout()
    out = OUT_DIR / "far_cer_by_meeting.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {out.name}")


# ================================================================
# 2. 近场 vs 远场 CER 对比图
# ================================================================
def plot_near_vs_far_cer(near_data: dict, far_data: dict):
    print("\n[2] 近场 vs 远场 CER 对比图...")

    # 按会议名聚合
    near_results = near_data.get("results", [])
    far_results = far_data.get("results", [])

    # 近场数据: 按会议分组
    near_by_meeting = {}
    for r in near_results:
        # "R8001_M8004_N_SPK8013" → "R8001_M8004"
        parts = r["name"].split("_")
        meeting = f"{parts[0]}_{parts[1]}"
        if meeting not in near_by_meeting:
            near_by_meeting[meeting] = []
        near_by_meeting[meeting].append(r["cer"])

    # 计算平均 CER 每场会议
    near_avg = {m: sum(cers) / len(cers) for m, cers in near_by_meeting.items()}
    far_avg = {r["name"]: r["cer"] for r in far_results}

    # 找共同会议
    common = sorted(set(near_avg.keys()) & set(far_avg.keys()))
    if not common:
        print("  [SKIP] 没有共同会议")
        return

    near_vals = [near_avg[m] * 100 for m in common]
    far_vals = [far_avg[m] * 100 for m in common]

    x = np.arange(len(common))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5.5))

    bars_near = ax.bar(x - width / 2, near_vals, width, label="近场 (Near)", color=NEAR_COLOR, edgecolor="white")
    bars_far = ax.bar(x + width / 2, far_vals, width, label="远场 (Far)", color=FAR_COLOR, edgecolor="white")

    # 标注数值
    for bar, val in zip(bars_near, near_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=8, color=NEAR_COLOR)
    for bar, val in zip(bars_far, far_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=8, color=FAR_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(common, fontsize=9)
    ax.set_ylabel("平均 CER (%)", fontsize=11)
    ax.set_title("近场 vs 远场 ASR — 每场会议平均 CER 对比", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))

    # 标注差距
    for i, (nv, fv) in enumerate(zip(near_vals, far_vals)):
        diff = fv - nv
        ax.annotate(
            f"+{diff:.1f}pp",
            xy=(i + width / 2, fv),
            xytext=(i + width / 2, fv + 5),
            ha="center", fontsize=8, color="red", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="red", lw=0.8),
        )

    fig.tight_layout()
    out = OUT_DIR / "near_vs_far_cer.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {out.name}")


# ================================================================
# 3. 远场 vs 近场 CER 相关性散点图
# ================================================================
def plot_far_vs_near_scatter(near_data: dict, far_data: dict):
    print("\n[3] 远场 vs 近场 CER 相关性散点图...")

    # 近场按说话人分组去找对应关系
    near_results = near_data.get("results", [])
    far_results = far_data.get("results", [])

    fig, ax = plt.subplots(figsize=(8, 6))

    # 每个远场会议 → 近场该会议所有说话人的 CER 分布
    far_by_meeting = {r["name"]: r["cer"] * 100 for r in far_results}

    near_by_meeting = {}
    for r in near_results:
        parts = r["name"].split("_")
        meeting = f"{parts[0]}_{parts[1]}"
        if meeting not in near_by_meeting:
            near_by_meeting[meeting] = []
        near_by_meeting[meeting].append(r["cer"] * 100)

    common = sorted(set(near_by_meeting.keys()) & set(far_by_meeting.keys()))

    # 散点: x=近场平均CER, y=远场CER
    x_vals = []
    y_vals = []
    labels = []
    for m in common:
        near_cers = near_by_meeting[m]
        x_vals.append(np.mean(near_cers))
        y_vals.append(far_by_meeting[m])
        labels.append(m)

    ax.scatter(x_vals, y_vals, c=FAR_COLOR, s=120, alpha=0.8, edgecolors="white", linewidth=0.5, zorder=3)

    # 标注
    for i, label in enumerate(labels):
        ax.annotate(label, (x_vals[i], y_vals[i]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, alpha=0.8)

    # y=x 参考线
    max_val = max(max(x_vals), max(y_vals)) * 1.1
    ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3, linewidth=1, label="y=x (相等)")

    # 趋势线
    if len(x_vals) > 1:
        z = np.polyfit(x_vals, y_vals, 1)
        p = np.poly1d(z)
        x_line = np.linspace(0, max_val, 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.5, linewidth=1, label="趋势线")

    ax.set_xlabel("近场平均 CER (%)", fontsize=11)
    ax.set_ylabel("远场 CER (%)", fontsize=11)
    ax.set_title("远场 vs 近场 CER 相关性", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, max_val)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = OUT_DIR / "far_vs_near_scatter.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {out.name}")


# ================================================================
# 汇总表格输出
# ================================================================
def print_summary_table(near_data: dict, far_data: dict):
    print("\n" + "=" * 60)
    print("远场 vs 近场 CER 汇总")
    print("=" * 60)

    if far_data:
        far_avg = far_data.get("avg_cer", 0) * 100
        far_max = far_data.get("max_cer", 0) * 100
        far_min = far_data.get("min_cer", 0) * 100
        far_n = far_data.get("num_files", 0)
        print(f"\n[远场 Far]")
        print(f"  评估会议数: {far_n}")
        print(f"  平均 CER:   {far_avg:.2f}%")
        print(f"  最高 CER:   {far_max:.2f}%")
        print(f"  最低 CER:   {far_min:.2f}%")

    if near_data:
        near_avg = near_data.get("avg_cer", 0) * 100
        near_max = near_data.get("max_cer", 0) * 100
        near_min = near_data.get("min_cer", 0) * 100
        near_n = near_data.get("num_files", 0)
        print(f"\n[近场 Near]")
        print(f"  评估 Speaker 数: {near_n}")
        print(f"  平均 CER:   {near_avg:.2f}%")
        print(f"  最高 CER:   {near_max:.2f}%")
        print(f"  最低 CER:   {near_min:.2f}%")

    if far_data and near_data:
        diff = far_avg - near_avg
        print(f"\n  差距 (远场 - 近场): +{diff:.2f}pp")


# ================================================================
# Main
# ================================================================
def main():
    print("=" * 60)
    print("远场 ASR 评估图表生成器")
    print("=" * 60)

    near_data = load_results(NEAR_PATH)
    far_data = load_results(FAR_PATH)

    if not near_data and not far_data:
        print("没有可用的数据！")
        return

    if near_data:
        print(f"  近场数据: {near_data.get('num_files', 0)} 个文件, "
              f"平均 CER {near_data.get('avg_cer', 0):.2%}")

    if far_data:
        print(f"  远场数据: {far_data.get('num_files', 0)} 个文件, "
              f"平均 CER {far_data.get('avg_cer', 0):.2%}")

    # 图表 1: 远场条形图
    if far_data:
        plot_far_cer_by_meeting(far_data)

    # 图表 2+3: 对比 (需要两者都有)
    if near_data and far_data:
        plot_near_vs_far_cer(near_data, far_data)
        plot_far_vs_near_scatter(near_data, far_data)
    else:
        if not near_data:
            print("\n  [SKIP] 对比图表需要近场数据")
        if not far_data:
            print("\n  [SKIP] 对比图表需要远场数据")

    # 汇总表格
    print_summary_table(near_data, far_data)

    print("\n全部完成！")


if __name__ == "__main__":
    main()
