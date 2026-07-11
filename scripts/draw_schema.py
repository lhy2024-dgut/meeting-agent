"""生成两张数据库图片：
1. 变更摘要表（新增字段/索引/约束一览）
2. 完整数据库 ER 图
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as mpatches

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = "docs/v1.5"


def draw_summary_table():
    """图1: 变更摘要表"""
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")

    title = ax.text(7, 6.5, "V1.5 数据库变更摘要", ha="center", va="center",
                    fontsize=18, fontweight="bold")

    # ── meetings 表区块 ──
    meetings_data = [
        ("meetings", "short_summary", "VARCHAR(500)", "200字中文摘要"),
        ("meetings", "project_name", "VARCHAR(255)", "项目名称"),
    ]

    # ── meeting_chunks 表区块 ──
    chunks_data = [
        ("meeting_chunks", "chunk_type", "VARCHAR(32)", "transcript/minutes/action_item/resolution"),
        ("meeting_chunks", "chunk_index", "INTEGER", "同类型内序号"),
        ("meeting_chunks", "content_hash", "VARCHAR(64)", "SHA256 去重指纹"),
        ("meeting_chunks", "created_at", "DATETIME", "索引写入时间"),
        ("meeting_chunks", "— (约束)", "UNIQUE(meeting_id, chunk_type, chunk_index)", "数据库层兜底"),
        ("meeting_chunks", "— (索引)", "INDEX(meeting_id, chunk_type, chunk_index)", "复合查询加速"),
        ("meeting_chunks", "— (索引)", "INDEX(content_hash)", "去重校验加速"),
    ]

    # 表格
    col_labels = ["表", "字段 / 类型", "定义", "说明"]
    all_rows = meetings_data + chunks_data

    # 用 text 手绘
    y_start = 5.8
    row_h = 0.58

    # 表头
    headers = ["表", "字段/类型", "定义", "说明"]
    col_x = [0.5, 2.8, 7.5, 10.5]
    col_w = [2.1, 4.5, 2.8, 3.2]

    # Draw header
    for j, (hdr, cx, cw) in enumerate(zip(headers, col_x, col_w)):
        rect = FancyBboxPatch((cx, y_start), cw, row_h,
                              boxstyle="round,pad=0.02", facecolor="#2c3e50",
                              edgecolor="#1a252f", linewidth=0.5)
        ax.add_patch(rect)
        ax.text(cx + cw/2, y_start + row_h/2, hdr, ha="center", va="center",
                fontsize=9, fontweight="bold", color="white")

    # Draw rows
    colors = ["#ecf0f1", "#ffffff"]
    for i, (tbl, field, defn, desc) in enumerate(all_rows):
        y = y_start - (i + 1) * row_h
        color = colors[i % 2]
        vals = [tbl, field, defn, desc]

        # 判断是否新增行
        is_new = field not in ["— (约束)", "— (索引)"]

        for j, (val, cx, cw) in enumerate(zip(vals, col_x, col_w)):
            if is_new and j == 1:
                fc = "#d5f5e3"  # 绿色底表示新增字段
            else:
                fc = color

            rect = FancyBboxPatch((cx, y), cw, row_h,
                                  boxstyle="round,pad=0.02", facecolor=fc,
                                  edgecolor="#bdc3c7", linewidth=0.3)
            ax.add_patch(rect)
            fw = "bold" if (is_new and j == 1) else "normal"
            fs = 8
            ax.text(cx + cw/2, y + row_h/2, val, ha="center", va="center",
                    fontsize=fs, fontweight=fw, color="#2c3e50")

    # 图例
    legend_y = y_start - (len(all_rows) + 1) * row_h - 0.3
    p1 = mpatches.Patch(color="#d5f5e3", label="新增字段")
    p2 = mpatches.Patch(color="#ecf0f1", label="新增约束/索引")
    leg = ax.legend(handles=[p1, p2], loc="upper center",
                    bbox_to_anchor=(0.5, -0.02), ncol=2, fontsize=9)
    ax.add_artist(leg)

    path = f"{OUT_DIR}/schema_changes.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[OK] {path}")
    return path


def draw_er_diagram():
    """图2: 完整数据库 ER 图"""
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(8, 9.6, "Meeting Agent — 数据库完整 ER 图", ha="center", va="center",
            fontsize=18, fontweight="bold")

    # ── 表定义 ──
    # meetings (左)
    meetings_cols = [
        ("id", "INTEGER", "PK"),
        ("title", "VARCHAR(255)", ""),
        ("created_at", "DATETIME", ""),
        ("updated_at", "DATETIME", ""),
        ("audio_path", "VARCHAR(500)", ""),
        ("duration_category", "VARCHAR(50)", ""),
        ("environment", "VARCHAR(100)", ""),
        ("file_hash", "VARCHAR(64)", "INDEX"),
        ("minutes_text", "TEXT", ""),
        ("action_items_text", "TEXT", ""),
        ("resolutions_text", "TEXT", ""),
        ("short_summary", "VARCHAR(500)", "★ NEW"),
        ("project_name", "VARCHAR(255)", "★ NEW"),
    ]

    # transcriptions (中上)
    trans_cols = [
        ("id", "INTEGER", "PK"),
        ("meeting_id", "INTEGER", "FK → meetings.id"),
        ("text", "TEXT", ""),
        ("timestamp", "FLOAT", ""),
        ("start_time", "FLOAT", ""),
        ("end_time", "FLOAT", ""),
        ("audio_segment", "VARCHAR(500)", ""),
        ("summary", "TEXT", ""),
    ]

    # meeting_chunks (右)
    chunks_cols = [
        ("id", "INTEGER", "PK"),
        ("meeting_id", "INTEGER", "FK → meetings.id"),
        ("chunk_type", "VARCHAR(32)", "★ NEW"),
        ("chunk_index", "INTEGER", "★ NEW"),
        ("chunk_text", "TEXT", ""),
        ("content_hash", "VARCHAR(64)", "★ NEW"),
        ("embedding", "VECTOR", ""),
        ("created_at", "DATETIME", "★ NEW"),
    ]

    # 约束框
    chunks_constraints = [
        "UNIQUE(meeting_id, chunk_type, chunk_index)",
        "INDEX(meeting_id, chunk_type, chunk_index)",
        "INDEX(content_hash)",
    ]

    tables = [
        ("meetings", meetings_cols, 1.0, 1.5, 4.5, 13),
        ("transcriptions", trans_cols, 6.0, 3.8, 4.5, 8),
        ("meeting_chunks", chunks_cols, 11.0, 1.5, 4.5, 8),
    ]

    def draw_table(ax, name, cols, x, y, w, n_visible, highlight_from=None):
        """画一张表"""
        row_h = 0.42
        # 标题行
        rect = FancyBboxPatch((x, y), w, row_h,
                              boxstyle="round,pad=0.02", facecolor="#2c3e50",
                              edgecolor="#1a252f", linewidth=0.5)
        ax.add_patch(rect)
        ax.text(x + w/2, y + row_h/2, name, ha="center", va="center",
                fontsize=10, fontweight="bold", color="white")

        # 列
        for i, (col, col_type, note) in enumerate(cols):
            cy = y - (i + 1) * row_h
            is_new = "NEW" in note

            col_rect = FancyBboxPatch((x, cy), w, row_h,
                                      boxstyle="round,pad=0.02",
                                      facecolor="#d5f5e3" if is_new else "#ffffff",
                                      edgecolor="#bdc3c7", linewidth=0.3)
            ax.add_patch(col_rect)

            # PK / FK 标记
            pk_fk = ""
            if "PK" in note:
                pk_fk = " 🔑"
            elif "FK" in note:
                pk_fk = " 🔗"

            cname = f"  {col}{pk_fk}"
            ax.text(x + 0.15, cy + row_h/2, cname, ha="left", va="center",
                    fontsize=7.5, fontweight="bold" if is_new else "normal",
                    color="#2c3e50")
            ax.text(x + w - 0.3, cy + row_h/2, col_type, ha="right", va="center",
                    fontsize=7, color="#7f8c8d", style="italic")

    for name, cols, x, y, w, n in tables:
        draw_table(ax, name, cols, x, y, w, n)

    # ── 关系连线 ──
    # meetings → transcriptions: 1:N
    # meetings 底部中心 → transcriptions 顶部中心
    ax.annotate("", xy=(8.25, 3.8 + 0.42), xytext=(3.25, 1.5),
                arrowprops=dict(arrowstyle="->", color="#e74c3c", lw=2,
                                connectionstyle="arc3,rad=0.3"))
    ax.text(5.9, 2.8, "1 : N\n(CASCADE)", ha="center", va="center",
            fontsize=8, color="#e74c3c", fontweight="bold")

    # meetings → meeting_chunks: 1:N
    ax.annotate("", xy=(13.25, 1.5 + 0.42), xytext=(5.5, 1.5),
                arrowprops=dict(arrowstyle="->", color="#e74c3c", lw=2,
                                connectionstyle="arc3,rad=-0.2"))
    ax.text(9.4, 2.3, "1 : N\n(CASCADE)", ha="center", va="center",
            fontsize=8, color="#e74c3c", fontweight="bold")

    # ── meeting_chunks 约束框 ──
    cy = 1.5 - 9 * 0.42 - 0.3  # below the table
    constraint_box_y = cy
    for i, c in enumerate(chunks_constraints):
        ax.text(13.25, constraint_box_y - i * 0.35, f"▸ {c}", fontsize=7,
                color="#8e44ad", fontfamily="monospace")

    # ── 图例 ──
    legend_y = 1.0
    p1 = mpatches.Patch(color="#d5f5e3", label="V1.5 新增字段")
    p2 = mpatches.Patch(color="#ffffff", label="已有字段", edgecolor="#bdc3c7")
    ax.legend(handles=[p1, p2], loc="upper center",
              bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=9)

    # ── 底部迁移链 ──
    chain = ("迁移链: d69ff883dd59 (initial) → a1b2c3d4e5f6 → "
             "86cee12a749a → 662a20a42c74 → 5ebf9e3a9002")
    ax.text(8, 0.4, chain, ha="center", va="center", fontsize=8,
            color="#95a5a6", fontfamily="monospace")

    path = f"{OUT_DIR}/schema_full_er.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[OK] {path}")
    return path


if __name__ == "__main__":
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    draw_summary_table()
    draw_er_diagram()
    print("Done — 两张图片已生成到 docs/v1.5/")
