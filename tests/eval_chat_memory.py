"""
Chat Memory 语义连续性评估脚本

用于评估「第 10 轮仍能引用第 1 轮上下文」的准确率。
需要 Ollama 运行在 localhost:11434，模型默认 qwen3.5:4b。

用法:
    python tests/eval_chat_memory.py              # 默认 5 个场景
    python tests/eval_chat_memory.py --rounds 5   # 自定义场景数
"""

import argparse
import sys
import time

from agents.chat_agent import ChatAgent

# ── 测试场景定义 ──
# 每个场景: (会议背景, 第1轮种子事实, 第10轮提问, 期望答案关键词)

SCENARIOS = [
    {
        "name": "人名 + 工号记忆",
        "transcript": "本次Q3预算评审会讨论了各部门预算分配方案。",
        "plant": "我叫张三，我的工号是BU-9527，请记住这个信息。",
        "query": "我的工号是多少？请直接回答工号。",
        "expected": ["9527", "BU-9527"],
        "filler_questions": [
            "本次会议讨论的主题是什么？",
            "预算分配方案有哪些要点？",
            "后续还需要什么材料？",
            "哪个部门预算最高？",
            "有没有需要特别关注的风险？",
            "下次会议什么时候？",
            "谁负责跟进预算执行？",
            "有没有部门提出异议？",
        ],
    },
    {
        "name": "关键数字记忆",
        "transcript": "本次年度规划会确定了2026年的营收目标和市场策略。",
        "plant": "注意，今年最重要的KPI目标是营收达到8800万元，比去年增长35%。",
        "query": "今年的营收KPI目标是多少？请直接回答数字。",
        "expected": ["8800", "8800万"],
        "filler_questions": [
            "会议的主要议题是什么？",
            "市场策略具体包含哪些？",
            "去年的营收基准是多少？",
            "哪个产品线增长最快？",
            "人员配置需要调整吗？",
            "竞争对手的情况如何？",
            "预算是否充足？",
            "Q1的里程碑是什么？",
        ],
    },
    {
        "name": "截止日期记忆",
        "transcript": "本次项目启动会明确了各阶段的交付时间节点。",
        "plant": "所有模块必须在10月15日之前完成联调，11月1日正式上线。",
        "query": "项目联调的截止日期是什么时候？请直接回答日期。",
        "expected": ["10月15", "10月15日"],
        "filler_questions": [
            "项目分为几个阶段？",
            "每个阶段的主要任务是什么？",
            "测试环境什么时候准备好？",
            "谁负责前后端联调？",
            "如果延期怎么处理？",
            "性能基准是什么？",
            "安全审查安排在什么时候？",
            "上线后谁来运维？",
        ],
    },
    {
        "name": "负责人记忆",
        "transcript": "本次产品评审会讨论了新功能的需求方案和排期。",
        "plant": "最终决定由李思思担任这个项目的技术负责人，她的邮箱是liss@company.cn。",
        "query": "这个项目的技术负责人是谁？请直接回答姓名。",
        "expected": ["李思思"],
        "filler_questions": [
            "新功能的核心需求是什么？",
            "用户反馈的主要问题有哪些？",
            "竞品是怎么做的？",
            "技术方案有什么风险？",
            "预计开发周期多长？",
            "需要哪些资源支持？",
            "是否有替代方案？",
            "排期冲突怎么解决？",
        ],
    },
    {
        "name": "决策结论记忆",
        "transcript": "本次技术选型评审会比较了三种方案的优劣。",
        "plant": "经过投票，最终决定采用方案B——微服务架构，预计6个月完成迁移。",
        "query": "技术选型的最终决定是什么？请直接回答选择的方案。",
        "expected": ["方案B", "微服务架构", "微服务"],
        "filler_questions": [
            "三种方案分别是什么？",
            "方案A为什么被否决？",
            "迁移的难点在哪里？",
            "团队对新架构的熟悉程度如何？",
            "有没有过渡期方案？",
            "成本对比是多少？",
            "是否考虑过混合方案？",
            "什么时候开始执行？",
        ],
    },
]


def run_evaluation(scenarios: list[dict], verbose: bool = True) -> dict:
    """运行全部场景评估，返回汇总结果"""
    results = []
    agent = ChatAgent()

    for idx, s in enumerate(scenarios, 1):
        if verbose:
            print(f"\n{'='*60}")
            print(f"场景 {idx}/{len(scenarios)}: {s['name']}")
            print(f"{'='*60}")

        # 注入会议上下文
        agent.set_meeting_context(
            transcript=s["transcript"],
            minutes=f"会议纪要：{s['transcript']}",
            meeting_id=f"eval_{idx}",
        )

        # 第 1 轮：植入种子事实
        resp_1 = agent.chat(s["plant"])
        if verbose:
            print(f"  [第 1 轮] Q: {s['plant'][:50]}...")
            print(f"  [第 1 轮] A: {resp_1[:80]}...")

        # 第 2-9 轮：填充问题
        for r, fq in enumerate(s["filler_questions"], 2):
            resp = agent.chat(fq)
            if verbose:
                print(f"  [第 {r} 轮] Q: {fq} → A: {resp[:60]}...")

        # 第 10 轮：测试记忆
        resp_10 = agent.chat(s["query"])
        passed = any(exp in resp_10 for exp in s["expected"])
        if verbose:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  [第 10 轮] Q: {s['query']}")
            print(f"  [第 10 轮] A: {resp_10}")
            print(f"  [结果] {status} (期望关键词: {s['expected']})")

        results.append(
            {
                "scenario": s["name"],
                "passed": passed,
                "response": resp_10,
                "expected": s["expected"],
                "stats": agent.get_memory_stats(),
            }
        )

    return results


def print_summary(results: list[dict], elapsed: float):
    """打印汇总报告"""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    rate = passed / total * 100 if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"评估总结")
    print(f"{'='*60}")
    print(f"  总场景数 : {total}")
    print(f"  通过数   : {passed}")
    print(f"  失败数   : {total - passed}")
    print(f"  准确率   : {rate:.0f}%")
    print(f"  总耗时   : {elapsed:.1f}s")
    print()

    if rate < 80:
        print(f"⚠️ 准确率 {rate:.0f}% 低于 80% 目标，需要排查以下场景：")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['scenario']}: 期望关键词 {r['expected']}, 实际回答: {r['response'][:100]}")
    else:
        print(f"✅ 准确率 {rate:.0f}% 达标 (≥ 80%)")

    # 输出每个场景的详细 stats
    print(f"\n各场景 Memory 统计:")
    for r in results:
        s = r["stats"]
        print(f"  {r['scenario']}: round={s['round_count']}, is_full={s['is_full']}, trimmed={s['trimmed']}")


def main():
    parser = argparse.ArgumentParser(description="Chat Memory 语义连续性评估")
    parser.add_argument("--scenarios", type=int, default=0,
                        help="运行场景数 (默认全部)")
    parser.add_argument("--quiet", action="store_true",
                        help="只输出汇总结果")
    args = parser.parse_args()

    scenarios = SCENARIOS[: args.scenarios] if args.scenarios else SCENARIOS

    print(f"Chat Memory 评估开始 — {len(scenarios)} 个场景")
    print(f"模型: qwen3.5:4b (默认)")
    print()

    start = time.time()
    try:
        results = run_evaluation(scenarios, verbose=not args.quiet)
    except Exception as e:
        print(f"\n❌ 评估异常: {e}")
        print("请确认 Ollama 已启动 (ollama serve) 且模型已拉取 (ollama pull qwen3.5:4b)")
        sys.exit(1)

    elapsed = time.time() - start
    print_summary(results, elapsed)

    # 返回退出码供 CI 使用
    passed = sum(1 for r in results if r["passed"])
    sys.exit(0 if passed / len(results) >= 0.8 else 1)


if __name__ == "__main__":
    main()
