"""TextGrid 文件解析器 — 解析 AliMeeting 标注文件"""

import json
import re
from pathlib import Path


def parse_textgrid(filepath: str | Path) -> dict:
    """解析单个 TextGrid 文件，返回结构化数据

    Args:
        filepath: .TextGrid 文件路径

    Returns:
        {
            "file": 原始文件名,
            "tiers": [
                {
                    "name": "说话人ID",
                    "intervals": [
                        {"start": 6.9, "end": 18.29, "text": "好嗯，咱们今天..."},
                        ...
                    ]
                },
                ...
            ],
            "full_text": "所有说话人文字拼接（含说话人标记）",
            "full_text_clean": "所有说话人文字拼接（不含说话人标记）",
        }
    """
    filepath = Path(filepath)
    content = filepath.read_text("utf-8")

    result = {
        "file": filepath.name,
        "tiers": [],
        "full_text": "",
        "full_text_clean": "",
    }

    # 用正则切出每个 tier
    # tier 的格式:
    #   item [1]:
    #       class = "IntervalTier"
    #       name = "SPK8013"
    #       ...
    #       intervals [1]:
    #           xmin = 6.9
    #           xmax = 18.29
    #           text = "..."
    #       intervals [2]:
    #           ...

    tier_pattern = re.compile(
        r'item\s*\[\d+\]:\s*'
        r'class\s*=\s*"IntervalTier"\s*'
        r'name\s*=\s*"([^"]*)"\s*'
        r'xmin\s*=\s*[\d.]+\s*'
        r'xmax\s*=\s*[\d.]+\s*'
        r'intervals:\s*size\s*=\s*\d+'
        r'(.*?)(?=item\s*\[\d+\]:|\Z)',
        re.DOTALL,
    )

    interval_pattern = re.compile(
        r'intervals\s*\[\d+\]:\s*'
        r'xmin\s*=\s*([\d.eE+-]+)\s*'
        r'xmax\s*=\s*([\d.eE+-]+)\s*'
        r'text\s*=\s*"([^"]*)"',
    )

    for tier_match in tier_pattern.finditer(content):
        speaker = tier_match.group(1)
        tier_body = tier_match.group(2)

        intervals = []
        for interval_match in interval_pattern.finditer(tier_body):
            intervals.append({
                "start": float(interval_match.group(1)),
                "end": float(interval_match.group(2)),
                "text": interval_match.group(3).strip(),
            })

        # 过滤掉空文本的 interval（纯沉默）
        intervals = [iv for iv in intervals if iv["text"]]

        result["tiers"].append({
            "name": speaker,
            "intervals": intervals,
        })

    # 拼接 full_text
    text_parts = []
    text_parts_clean = []
    for tier in result["tiers"]:
        for iv in tier["intervals"]:
            text_parts.append(f"[{tier['name']}] {iv['text']}")
            text_parts_clean.append(iv["text"])

    result["full_text"] = " ".join(text_parts)
    result["full_text_clean"] = " ".join(text_parts_clean)

    return result


def parse_all_textgrids(directory: str | Path) -> list[dict]:
    """解析目录下所有 .TextGrid 文件

    Args:
        directory: 包含 .TextGrid 文件的目录

    Returns:
        解析结果列表
    """
    directory = Path(directory)
    results = []
    for f in sorted(directory.glob("*.TextGrid")):
        try:
            data = parse_textgrid(f)
            results.append(data)
            print(f"  OK {f.name}: {len(data['tiers'])} 人, "
                  f"共 {sum(len(t['intervals']) for t in data['tiers'])} 句话, "
                  f"{len(data['full_text_clean'])} 字")
        except Exception as e:
            print(f"  FAIL {f.name}: 解析失败 - {e}")
    return results


def save_as_json(data: list[dict], output_path: str | Path) -> None:
    """把解析结果存为 JSON"""
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n解析结果已保存到 {output_path}")
    print(f"共 {len(data)} 个文件")


if __name__ == "__main__":
    import sys

    # 默认解析远场数据
    base = Path(__file__).resolve().parent.parent
    far_textgrid_dir = base / "data" / "alimeeting" / "Eval_Ali" / "Eval_Ali_far" / "textgrid_dir"
    near_textgrid_dir = base / "data" / "alimeeting" / "Eval_Ali" / "Eval_Ali_near" / "textgrid_dir"
    output_dir = base / "evaluation"

    # 远场
    print("=" * 60)
    print("解析远场（Far）TextGrid...")
    print("=" * 60)
    far_results = parse_all_textgrids(far_textgrid_dir)
    save_as_json(far_results, output_dir / "alimeeting_far_parsed.json")

    # 近场
    print("\n" + "=" * 60)
    print("解析近场（Near）TextGrid...")
    print("=" * 60)
    near_results = parse_all_textgrids(near_textgrid_dir)
    save_as_json(near_results, output_dir / "alimeeting_near_parsed.json")
