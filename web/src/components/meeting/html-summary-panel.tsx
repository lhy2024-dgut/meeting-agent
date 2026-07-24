"use client";

import { useEffect, useState } from "react";

import { generateHtmlSummary } from "@/lib/api";
import { requestBrowserJson } from "@/lib/browser-api";
import { HtmlSummaryResponse } from "@/types/api";
import { Card } from "@/components/ui/cards";

type HtmlSummaryPanelProps = {
  meetingId: number;
  unlockToken?: string | null;
};

export function HtmlSummaryPanel({ meetingId, unlockToken = null }: HtmlSummaryPanelProps) {
  const [summary, setSummary] = useState<HtmlSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"visual" | "source">("visual");
  // 是否在可视化纪要中渲染代码块 / 流程图（原按钮已移除，使用固定默认值）
  const includeCode = false;
  const includeFlowchart = true;

  useEffect(() => {
    let active = true;
    // 用 requestBrowserJson 代替 getHtmlSummary（api.ts），避免 401 触发
    // handleUnauthorized → 清除 token → 跳转登录的死循环。
    // 404（尚未生成）和 401（token 短暂失效）均静默处理，只展示"生成"按钮。
    requestBrowserJson<HtmlSummaryResponse>(`/meetings/${meetingId}/html-summary`, {
      headers: unlockToken ? { "X-Meeting-Unlock-Token": unlockToken } : undefined,
    })
      .then((nextSummary) => {
        if (active) setSummary(nextSummary);
      })
      .catch(() => {
        // 404 或 401：纪要尚未生成，不弹错误
      });
    return () => {
      active = false;
    };
  }, [meetingId, unlockToken]);

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const nextSummary = await generateHtmlSummary(meetingId, {
        show_code: includeCode,
        show_flowchart: includeFlowchart,
      }, {
        headers: unlockToken ? { "X-Meeting-Unlock-Token": unlockToken } : undefined,
      });
      setSummary(nextSummary);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "生成可视化纪要失败");
    } finally {
      setLoading(false);
    }
  }

  function handleDownload() {
    if (!summary) return;
    const blob = new Blob([summary.html], { type: "text/html;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = summary.file_name;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="section-card-title !mb-1">{"纪要可视化概览"}</h2>
          <div className="text-[13px] text-[var(--text-secondary)]">{"生成一份可预览、可下载的 HTML 纪要总览。"}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="primary-button" type="button" onClick={handleGenerate} disabled={loading}>
            {loading ? "生成中..." : "生成可视化纪要"}
          </button>
        </div>
      </div>

      {summary ? (
        <div className="flex flex-wrap gap-2">
          <button className={viewMode === "visual" ? "secondary-button" : "tertiary-button"} type="button" onClick={() => setViewMode("visual")}>{"预览"}</button>
          <button className={viewMode === "source" ? "secondary-button" : "tertiary-button"} type="button" onClick={() => setViewMode("source")}>{"HTML 源码"}</button>
          <button className="tertiary-button" type="button" onClick={handleDownload}>{"下载 HTML"}</button>
        </div>
      ) : null}

      {error ? <div className="error-inline">{error}</div> : null}

      {summary ? (
        viewMode === "visual" ? (
          <iframe
            className="min-h-[680px] w-full rounded-[18px] border border-[var(--border)] bg-white"
            srcDoc={summary.html}
            title="HTML 纪要预览"
          />
        ) : (
          <pre className="overflow-x-auto rounded-[18px] border border-[var(--border)] bg-[#0f172a] p-4 text-[12px] leading-6 text-slate-100">
            <code>{summary.html}</code>
          </pre>
        )
      ) : (
        <div className="rounded-[18px] border border-dashed border-[var(--border)] bg-white/80 p-6 text-[13px] text-[var(--muted)]">
          {"点击上方按钮生成 HTML 可视化纪要。"}
        </div>
      )}
    </Card>
  );
}
