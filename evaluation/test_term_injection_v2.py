"""术语词表注入 ASR 对比测试 — 四场景 × 多词表规模
每个场景分别测：0 词条 / 5 词条 / 10 词条 / 全部词条
观察 CER 随词表规模的变化趋势。
"""

import json
import sys
import time
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from engines.asr_engine import ASREngine
from jiwer import cer

# ── 音频 ──
AUDIO_LAW = BASE_DIR / "律所案件研讨会（法律约2分钟）.mp3"
AUDIO_MED = BASE_DIR / "医院科室晨会交班（医疗约2分钟）.mp3"
AUDIO_MFG = BASE_DIR / "工厂产线质量分析会（制造业约2分钟）.mp3"
AUDIO_FIN = BASE_DIR / "银行支行周例会（金融-带语气词2分钟）.mp3"

# ── 参考文本 ──
REFERENCE_LAW = (
    "各位同事，今天开这个案件研讨会，主要讨论三个案子。"
    "先说第一个，王建平诉恒达房地产开发公司的商品房买卖合同纠纷。"
    "原告二零二一年三月与被告签订了翡翠湾三期的认购协议书，支付了定金三十万元。"
    "但到了约定的网签时间，被告以预售许可证尚在办理中为由拒绝签约。"
    "我们的代理意见是，根据民法典第四百九十五条，认购书已经具备商品房买卖合同的主要条款，"
    "包括房屋坐落、面积、单价和付款方式，应当认定为预约合同已转化为本约合同。"
    "被告至今未取得预售许可证，属于根本违约，应当双倍返还定金。"
    "同时我们还要主张差价损失，因为翡翠湾三期同户型现在的备案价已经比二零二一年涨了将近百分之二十。"
    "第二个案子是张美华的离婚纠纷，涉及夫妻共同财产分割。"
    "男方是阿里系 P8 级别高级算法工程师，年薪大概在一百二十万左右，还有三万股的期权尚未归属。"
    "我们的策略是申请法院调查令，调取男方近三年的银行流水和阿里巴巴的期权授予协议。"
    "关键争议在于男方婚前购入的一套杭州未来科技城的房产，婚后用共同收入还了部分贷款，"
    "这部分对应的增值应当认定为夫妻共同财产。"
    "第三个是今天刚接的商标侵权案，茶颜悦色诉茶颜观色，原告要求赔偿经济损失三百万元。"
    "好，大家先看一下证据材料，等下逐案讨论诉讼策略。"
)

REFERENCE_MED = (
    "好，现在开始呼吸内科晨会交班。昨晚值班医生陈思远先汇报一下新收病人情况。"
    "急诊昨晚送上来一个慢阻肺急性加重的病人，刘国华，男，六十八岁，"
    "既往有高血压病史二十年，长期口服硝苯地平控释片。"
    "入科时指脉氧饱和度只有百分之八十八，血气分析提示二氧化碳分压六十五毫米汞柱，"
    "氧分压五十五毫米汞柱。我们立即给予了无创呼吸机辅助通气，型号是飞利浦伟康 V60，"
    "设置 IPAP 十六厘米水柱，EPAP 四厘米水柱，吸入氧浓度百分之三十五。"
    "同时上了甲泼尼龙琥珀酸钠四十毫克静脉注射，联合布地奈德雾化吸入。"
    "到今早六点复查血气，二氧化碳分压已经降到四十八，氧分压升到七十二，病人情况趋稳。"
    "另外三床张文秀的痰培养结果回来了，是耐碳青霉烯的铜绿假单胞菌，"
    "药敏显示替加环素和多黏菌素B敏感。我们已经跟临床药学科会诊过了，"
    "建议调整抗感染方案为替加环素首剂两百毫克维持一百毫克联合多黏菌素B雾化吸入，疗程至少两周。"
    "对了，五床的胸部CT提示右下肺占位性病变，大小约三点二乘二点八厘米，"
    "分叶征和毛刺征都很明显，高度怀疑周围型肺癌。"
    "我已经开了增强CT和PET-CT，肿瘤标志物也抽了，等结果出来再请胸外科会诊。"
    "好，以上就是昨晚的情况，大家有什么补充的吗？赵主任您看今天的重点事项怎么安排？"
)

REFERENCE_MFG = (
    "先通报一下上周的生产数据。三号车间两条SMT贴片线的直通率从百分之九十七点二降到了百分之九十三点五，"
    "主要缺陷是虚焊和立碑，集中在QFN-32封装和0402电阻这两个料号上。"
    "工艺组初步分析是回流焊炉温曲线出了问题，因为上周二我们更换了助焊剂品牌，"
    "从阿尔法OM-338换成了科利泰WS-618，新助焊剂的活性温度窗口比之前窄了大概十五摄氏度。"
    "今天中午之前请王师傅重新测一遍炉温曲线，用KIC测温仪跑三次，取平均值，数据发到质量群里。"
    "另外总装车间反馈说CID检测工位最近漏检率偏高，上周一共流出了七块不良板到成品库，客户投诉了两起。"
    "我跟设备科确认了一下，那台美陆MV-3000的AOI设备已经用了五年多，相机光源衰减严重，建议这个月安排一次大修。"
    "备件方面，需要更换四组同轴光源和两块FPGA控制板，采购申请我已经提交了。"
    "然后说一下安全生产的事。上周四冲压车间发生了一起轻微工伤，操作工李师傅在调试扬力J23-80冲床时手指被模具压伤，"
    "好在只是软组织挫伤。安环科调查下来，直接原因是设备的光电保护装置被短接了，这绝对是严重违规。"
    "我已经要求所有产线在今天下班前完成光电保护的全面自查，明天安环科抽查，查到问题直接停机整改。"
    "好，今天就这些，大家还有要补充的吗？"
)

REFERENCE_FIN = (
    "行，那咱们开始吧。这周主要对一下几个指标。"
    "首先是个人存款这个月的情况，截止到昨天，我们支行个人存款余额是九点七个亿，比上个月末少了大概三千万。"
    "这个讲实话，跟预期差不多，因为月初那波理财到期赎回的影响还没完全消化掉。"
    "张经理，你们理财团队这个月的重点还是把金葵花系列的理财产品推一下，"
    "就是年化百分之三点六五的那个，九十天期的，在同业里面还是有竞争力的。"
    "哎对，说到这个，中证征信中心上周发了个通知，说企业信贷的征信查询接口要升级到V3.0版本，"
    "就是说从七月一号开始老接口就不能用了。"
    "这个事技术那边我已经让李工去跟进了，但有个问题就是升级之后，我们行里的信贷审批系统也得做相应的接口适配，"
    "这个他们报的工期是两个星期。"
    "那我就想问问了，现在都六月中了，七月初就要切，万一中间出点啥状况，企业贷款这边不是要断档了吗？"
    "所以说，我的意思是，李工你们能不能跟总行的科技部协调一下，"
    "就是争取一个过渡期，让我们先跑一周的新老接口并行验证，没问题了再切过去。这样稳当一点嘛。"
    "好，然后是普惠金融的任务。区里给我们支行的指标是今年小微企业贷款增量要达到一个亿，"
    "我看了眼进度表，到现在才完成了不到四千万。下半年得加把劲了。"
    "小周，你那个金盾风控系统V4.2用得怎么样？那个系统上线之后审批效率有没有明显提升？"
)

# ── 各场景完整专有名词列表（按先常见/短词 → 后罕见/长词排序）──
ALL_TERMS = {
    "law": {  # 18 个
        "name": "律所案件研讨会（法律）",
        "audio": AUDIO_LAW,
        "reference": REFERENCE_LAW,
        "terms": [
            "王建平", "翡翠湾三期", "预售许可证", "张美华", "茶颜悦色",                     # 5
            "恒达房地产开发公司", "阿里系 P8", "茶颜观色", "认购协议书", "阿里巴巴",       # 10
            "期权授予协议", "杭州未来科技城", "高级算法工程师", "法院调查令", "共同财产",     # 15
            "民法典第四百九十五条", "诉讼策略", "商标侵权",                                  # 18
        ],
    },
    "med": {  # 17 个
        "name": "医院科室晨会交班（医疗）",
        "audio": AUDIO_MED,
        "reference": REFERENCE_MED,
        "terms": [
            "陈思远", "慢阻肺", "硝苯地平控释片", "飞利浦伟康 V60", "铜绿假单胞菌",           # 5
            "甲泼尼龙琥珀酸钠", "替加环素", "多黏菌素 B", "布地奈德", "张文秀",               # 10
            "耐碳青霉烯", "胸部 CT", "PET-CT", "肿瘤标志物", "胸外科",                       # 15
            "IPAP 十六", "EPAP 四",                                                          # 17
        ],
    },
    "mfg": {  # 18 个
        "name": "工厂产线质量分析会（制造业）",
        "audio": AUDIO_MFG,
        "reference": REFERENCE_MFG,
        "terms": [
            "直通率", "SMT 贴片线", "QFN-32 封装", "0402 电阻", "阿尔法 OM-338",              # 5
            "科利泰 WS-618", "KIC 测温仪", "CID 检测工位", "美陆 MV-3000", "AOI 设备",        # 10
            "FPGA 控制板", "扬力 J23-80 冲床", "同轴光源", "光电保护装置", "安环科",          # 15
            "回流焊", "助焊剂", "成品库",                                                     # 18
        ],
    },
    "fin": {  # 17 个
        "name": "银行支行周例会（金融·带语气词）",
        "audio": AUDIO_FIN,
        "reference": REFERENCE_FIN,
        "terms": [
            "金葵花系列", "中证征信中心", "信贷审批系统", "年化百分之三点六五", "总行科技部",   # 5
            "V3.0 版本", "金盾风控系统 V4.2", "新老接口并行", "普惠金融", "小微企业贷款",      # 10
            "过渡期", "审批效率", "个人存款", "七月一号", "增量",                             # 15
            "张经理", "李工",                                                                 # 17
        ],
    },
}


def get_duration_seconds(audio_path: Path) -> float:
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, timeout=10
        )
        return float(r.stdout.decode("utf-8", errors="replace").strip())
    except Exception:
        return 0


def run_test(asr: ASREngine, audio_path: Path, reference: str,
             terms: list[str] | None = None, label: str = "无词表") -> dict:
    print(f"\n  [{label}] 转写中...", end=" ", flush=True)
    initial_prompt = " ".join(terms) if terms else None
    t0 = time.time()
    segments, duration = asr.transcribe(str(audio_path), initial_prompt=initial_prompt)
    hypothesis = " ".join(seg["text"] for seg in segments)
    elapsed = time.time() - t0
    error_rate = cer(reference, hypothesis)
    print(f"CER={error_rate:.2%}, 耗时={elapsed:.1f}s")
    return {
        "label": label,
        "num_terms": len(terms) if terms else 0,
        "hypothesis": hypothesis,
        "cer": round(error_rate, 4),
        "cer_pct": f"{error_rate:.2%}",
        "elapsed_sec": round(elapsed, 1),
    }


def check_terms(hypothesis: str, terms: list[str]) -> dict:
    results = {}
    for term in terms:
        found = term.lower() in hypothesis.lower()
        results[term] = found
    return results


def main():
    print("=" * 60)
    print("术语词表注入测试 — 四场景 × 多词表规模")
    print("=" * 60)
    print("每个场景测 4 组：0 词条 / 5 词条 / 10 词条 / 全部词条")
    print("观察 CER 随词表规模的变化趋势")

    output_dir = BASE_DIR / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 初始化 ASR
    print("\n初始化 ASR 引擎...")
    asr = ASREngine()
    print("  [OK] 引擎就绪\n")

    all_scene_results = []

    for scene_key, scene in ALL_TERMS.items():
        scene_name = scene["name"]
        audio = scene["audio"]
        reference = scene["reference"]
        all_terms = scene["terms"]
        total = len(all_terms)

        dur = get_duration_seconds(audio)
        print(f"\n{'#' * 60}")
        print(f"# {scene_name}")
        print(f"# 音频 {audio.name} | {dur:.1f}s | 共 {total} 个专有名词")
        print(f"{'#' * 60}")

        # 定义 4 组词表规模
        sizes = [0, 5, 10, total]
        term_sets = {
            0: None,
            5: all_terms[:5],
            10: all_terms[:10],
            total: all_terms,
        }

        runs = []
        for size in sizes:
            label = f"词表{size}" if size else "无词表"
            r = run_test(asr, audio, reference, terms=term_sets[size], label=label)
            if r["num_terms"] > 0:
                term_results = check_terms(r["hypothesis"], term_sets[size])
                r["correct_terms"] = sum(1 for v in term_results.values() if v)
                r["total_terms"] = size
            else:
                # 无词表时，只检查是否正确全为 0（天然 0）
                r["correct_terms"] = 0
                r["total_terms"] = total  # 统一用总数为分母对比
            runs.append(r)

        # 追加无词表时用总词表检测
        term_no = check_terms(runs[0]["hypothesis"], all_terms)
        runs[0]["correct_terms"] = sum(1 for v in term_no.values() if v)
        runs[0]["total_terms"] = total

        scene_result = {"scene": scene_name, "key": scene_key, "total_terms": total, "runs": runs}
        all_scene_results.append(scene_result)

        # 打印本场景汇总
        print(f"\n  【{scene_name} 汇总】")
        print(f"  {'词表规模':<12} {'CER':<10} {'下降':<10} {'专名正确':<12}")
        print(f"  {'-' * 44}")
        baseline_cer = runs[0]["cer"]
        for r in runs:
            drop = (baseline_cer - r["cer"]) * 100
            print(f"  {r['label']:<12} {r['cer_pct']:<10} {'↓'+f'{drop:.2f}pp' if drop>0 else '-':<10} {r['correct_terms']}/{r['total_terms']:<9}")

    # ── 全局汇总 ──
    print(f"\n\n{'=' * 80}")
    print("全局汇总 — 词表规模对 CER 的影响")
    print(f"{'=' * 80}")

    print(f"\n{'场景':<26} {'0词条 CER':<12} {'5词条 CER':<12} {'10词条 CER':<13} {'全部CER':<12} {'最大下降':<10}")
    print(f"{'-' * 86}")
    for sr in all_scene_results:
        runs = {r["num_terms"]: r for r in sr["runs"]}
        base = runs[0]["cer"]
        max_drop = max((base - r["cer"]) * 100 for r in sr["runs"])
        print(f"{sr['scene']:<26} {runs[0]['cer_pct']:<12} {runs[5]['cer_pct']:<12} "
              f"{runs[10]['cer_pct']:<13} {runs[sr['total_terms']]['cer_pct']:<12} ↓{max_drop:<5.2f}pp")

    # 趋势图用文本
    print(f"\n\n--- CER 变化趋势 ---")
    print(f"{'场景':<26} {'→'.join(['0', '5', '10', '全部']):<30}")
    print(f"{'-' * 56}")
    for sr in all_scene_results:
        cers = " → ".join(f"{r['cer_pct']}" for r in sr["runs"])
        print(f"{sr['scene']:<26} {cers}")

    # 保存 JSON
    summary = {
        "test_date": "2026-06-09",
        "asr_model": "Faster-Whisper base (CPU int8, 中文)",
        "injection_method": "initial_prompt",
        "scenes": [],
    }
    for sr in all_scene_results:
        scene_entry = {
            "scene": sr["scene"],
            "key": sr["key"],
            "total_terms": sr["total_terms"],
            "runs": [
                {
                    "num_terms": r["num_terms"],
                    "label": r["label"],
                    "cer": r["cer"],
                    "cer_pct": r["cer_pct"],
                    "correct_terms": r["correct_terms"],
                    "total_terms": r["total_terms"],
                    "hypothesis": r["hypothesis"][:300],
                    "elapsed_sec": r["elapsed_sec"],
                }
                for r in sr["runs"]
            ],
        }
        summary["scenes"].append(scene_entry)

    summary_path = output_dir / "term_injection_scale_results.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果已保存到 {summary_path}")


if __name__ == "__main__":
    main()
