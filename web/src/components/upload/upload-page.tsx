"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useJobPolling } from "@/hooks/use-job-polling";
import { createMeetingProcessJob, getApiBaseUrl } from "@/lib/api";
import { markMeetingFresh } from "@/lib/privacy";
import { PrivacyModal, PrivacySelector, PrivacyValue } from "@/components/ui/privacy-choice";
import { TemplateOption, UploadMetadataResponse } from "@/types/api";

type UploadPageProps = {
  metadata: UploadMetadataResponse;
};

function getCompatibleOutputFormat(
  currentFormat: string,
  selectedTemplate: TemplateOption | null,
): string {
  if (!selectedTemplate) {
    return currentFormat;
  }

  const supportsCurrentFormat =
    currentFormat === "docx"
      ? selectedTemplate.has_docx
      : currentFormat === "pdf"
        ? selectedTemplate.has_pdf
        : true;

  if (supportsCurrentFormat) {
    return currentFormat;
  }
  if (selectedTemplate.has_docx) {
    return "docx";
  }
  if (selectedTemplate.has_pdf) {
    return "pdf";
  }
  return "md";
}

export function UploadPage({ metadata }: UploadPageProps) {
  const router = useRouter();
  const now = useMemo(() => new Date(), []);
  const apiBaseUrl = getApiBaseUrl();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState(`${now.getFullYear()}-${`${now.getMonth() + 1}`.padStart(2, "0")}-${`${now.getDate()}`.padStart(2, "0")}`);
  const [meetingTime, setMeetingTime] = useState(`${`${now.getHours()}`.padStart(2, "0")}:${`${now.getMinutes()}`.padStart(2, "0")}`);
  const [outputFormat, setOutputFormat] = useState(metadata.output_formats[0] ?? "docx");
  const [scene, setScene] = useState(metadata.scenes[0]?.scene ?? "");
  const [terms, setTerms] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templates, setTemplates] = useState<TemplateOption[]>(metadata.templates);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [privacy, setPrivacy] = useState<PrivacyValue>(null);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);

  const selectedTemplate = templates.find((item) => item.name === templateName) ?? null;
  const effectiveOutputFormat = getCompatibleOutputFormat(outputFormat, selectedTemplate);

  const { job, startPolling } = useJobPolling({
    onSucceeded: (nextJob) => {
      setSubmitting(false);
      if (nextJob.result?.meeting_id) {
        markMeetingFresh(nextJob.result.meeting_id);
        router.push(`/meetings/${nextJob.result.meeting_id}`);
      }
    },
    onFailed: (nextJob) => {
      setSubmitting(false);
      setError(nextJob.error || "任务执行失败");
    },
    onPollError: (pollError) => {
      setSubmitting(false);
      setError(pollError.message || "查询任务状态失败");
    },
  });

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请选择音频或视频文件");
      return;
    }
    // 未选择隐私 → 弹窗询问，选择后再继续
    if (privacy === null) {
      setError("");
      setShowPrivacyModal(true);
      return;
    }
    void runGenerate(privacy);
  }

  async function runGenerate(isPrivate: boolean) {
    if (!file) return;
    setSubmitting(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", title || file.name.replace(/\.[^.]+$/, ""));
      formData.append("meeting_date", meetingDate);
      formData.append("meeting_time", meetingTime);
      formData.append("output_format", effectiveOutputFormat);
      formData.append("scene", scene);
      formData.append("is_private", isPrivate ? "true" : "false");
      if (terms.trim()) formData.append("terms", terms.trim());
      if (templateName) formData.append("template_name", templateName);

      const created = await createMeetingProcessJob(formData);
      const initialJob = await startPolling(created.job_id);
      if (initialJob.status === "failed") {
        setSubmitting(false);
        setError(initialJob.error || "任务执行失败");
      }
      if (initialJob.status === "succeeded" && initialJob.result?.meeting_id) {
        setSubmitting(false);
        markMeetingFresh(initialJob.result.meeting_id);
        router.push(`/meetings/${initialJob.result.meeting_id}`);
      }
    } catch (submitError) {
      setSubmitting(false);
      setError(submitError instanceof Error ? submitError.message : "创建任务失败");
    }
  }

  function handlePrivacyModalChoose(value: boolean) {
    setPrivacy(value);
    setShowPrivacyModal(false);
    void runGenerate(value);
  }

  function handleTemplateChange(nextTemplateName: string) {
    setTemplateName(nextTemplateName);
    const nextTemplate = templates.find((item) => item.name === nextTemplateName) ?? null;
    setOutputFormat((current) => getCompatibleOutputFormat(current, nextTemplate));
  }

  async function handleTemplatesRefresh() {
    try {
      const response = await fetch(`${apiBaseUrl}/meta/upload`);
      if (response.ok) {
        const data = await response.json() as { templates: TemplateOption[] };
        setTemplates(data.templates ?? []);
      }
    } catch {
      // 刷新失败静默处理
    }
  }

  return (
    <div className="space-y-6">
      <div><h1 className="page-title">{"上传新会议"}</h1></div>

      <form className="space-y-6" onSubmit={handleSubmit}>
        <div className="panel-card space-y-5">
          <div>
            <label className="upload-dropzone">
              <span className="upload-dropzone-title">{"拖拽音频或视频文件到此处"}</span>
              <span className="upload-dropzone-subtitle">{"支持 wav / mp3 / m4a / ogg / flac / mp4 / avi / mov / mkv"}</span>
              <input className="hidden" type="file" accept=".wav,.mp3,.m4a,.ogg,.flac,.mp4,.avi,.mov,.mkv" onChange={(event) => { const nextFile = event.target.files?.[0] ?? null; setFile(nextFile); if (nextFile) setTitle(nextFile.name.replace(/\.[^.]+$/, "")); }} />
            </label>
            {file ? <div className="mt-3 text-[14px] text-[var(--text-secondary)]">{"已选择："}{file.name}</div> : null}
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="md:col-span-3"><input className="input-shell" value={title} onChange={(event) => setTitle(event.target.value)} placeholder={"会议标题"} /></div>
            <input className="input-shell" type="date" value={meetingDate} onChange={(event) => setMeetingDate(event.target.value)} />
            <input className="input-shell" type="time" value={meetingTime} onChange={(event) => setMeetingTime(event.target.value)} />
            <select className="input-shell" value={effectiveOutputFormat} onChange={(event) => setOutputFormat(event.target.value)}>{metadata.output_formats.map((format) => <option key={format} value={format}>{format}</option>)}</select>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <select className="input-shell" value={scene} onChange={(event) => setScene(event.target.value)}>{metadata.scenes.map((item) => <option key={item.scene} value={item.scene}>{item.display_name}</option>)}</select>
            <div className="info-strip text-[13px] text-[var(--text-secondary)]">{metadata.scenes.find((item) => item.scene === scene)?.description || "选择适合会议场景的纪要结构模板。"}</div>
          </div>

          <TemplatePicker apiBaseUrl={apiBaseUrl} outputFormat={effectiveOutputFormat} selectedTemplateName={templateName} templates={templates} onChange={handleTemplateChange} onTemplatesRefresh={() => void handleTemplatesRefresh()} />

          <div className="info-strip text-[13px] text-[var(--text-secondary)]">
            默认使用 SenseVoiceSmall 转写、512 字 RAG 切分和自动转写策略。
          </div>

          <textarea className="input-shell min-h-[120px]" value={terms} onChange={(event) => setTerms(event.target.value)} placeholder={"术语词表（每行一个，可选）"} />

          <PrivacySelector value={privacy} onChange={setPrivacy} />

          <div className="flex items-center gap-3">
            <button className="primary-button" type="submit" disabled={submitting}>{submitting ? "创建任务中..." : "开始生成会议纪要"}</button>
          </div>
        </div>
      </form>

      <PrivacyModal
        open={showPrivacyModal}
        onChoose={handlePrivacyModalChoose}
        onCancel={() => setShowPrivacyModal(false)}
      />

      {error ? <div className="error-inline">{error}</div> : null}

      {job ? (
        <div className="panel-card space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-[16px] font-bold text-[var(--dark)]">{"处理进度"}</div>
              <div className="text-[13px] text-[var(--text-secondary)]">{job.message}</div>
            </div>
            <div className="text-[14px] font-semibold text-[var(--primary)]">{job.progress_pct}%</div>
          </div>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${job.progress_pct}%` }} /></div>
          <div className="text-[12px] text-[var(--muted)]">{"状态："}{job.status}{" / 阶段："}{job.stage}</div>
          {job.error ? <div className="error-inline">{"任务失败："}{job.error}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

type TemplatePickerProps = { apiBaseUrl: string; outputFormat: string; selectedTemplateName: string; templates: TemplateOption[]; onChange: (value: string) => void; onTemplatesRefresh: () => void; };

function TemplatePicker({ apiBaseUrl, outputFormat, selectedTemplateName, templates, onChange, onTemplatesRefresh }: TemplatePickerProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  async function handleTemplateUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${apiBaseUrl}/meta/templates/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail || "上传失败");
      }
      onTemplatesRefresh();
    } catch (uploadErr) {
      setUploadError(uploadErr instanceof Error ? uploadErr.message : "上传失败");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-card-title mb-1">{"导出模板"}</div>
          <div className="text-[13px] text-[var(--text-secondary)]">{"选择模板后会按对应版式导出，支持直接预览封面样式。"}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={selectedTemplateName ? "secondary-button" : "primary-button"} type="button" onClick={() => onChange("")}>{"默认模板"}</button>
          <label className="tertiary-button cursor-pointer">
            {uploading ? "上传中..." : "上传模板"}
            <input className="hidden" type="file" accept=".docx,.pdf" disabled={uploading} onChange={(e) => void handleTemplateUpload(e)} />
          </label>
        </div>
      </div>

      {uploadError ? <div className="error-inline">{uploadError}</div> : null}

      {templates.length === 0 ? (
        <div className="text-[13px] text-[var(--muted)]">暂无自定义模板，点击「上传模板」添加 .docx 或 .pdf 模板文件。</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {templates.map((template) => {
            const selected = selectedTemplateName === template.name;
            const supportsCurrentFormat = outputFormat === "docx" ? template.has_docx : outputFormat === "pdf" ? template.has_pdf : true;
            return (
              <button key={template.name} className={`template-card ${selected ? "template-card-active" : ""}`.trim()} type="button" onClick={() => onChange(template.name)}>
                <div className="template-card-preview">
                  {template.preview_path ? <Image alt={`${template.label} 预览`} className="template-card-image" src={`${apiBaseUrl}${template.preview_path}`} width={640} height={400} unoptimized /> : <div className="template-card-placeholder">{"无预览图"}</div>}
                </div>
                <div className="space-y-2 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-[var(--dark)]">{template.label}</div>
                    {selected ? <span className="template-card-badge">{"已选择"}</span> : null}
                  </div>
                  <div className="flex flex-wrap gap-2 text-[12px]">
                    <span className={`template-format-pill ${template.has_docx ? "is-on" : "is-off"}`}>DOCX</span>
                    <span className={`template-format-pill ${template.has_pdf ? "is-on" : "is-off"}`}>PDF</span>
                    <span className="template-format-pill is-on">MD</span>
                  </div>
                  <div className={`text-[12px] ${supportsCurrentFormat ? "text-[var(--muted)]" : "text-[#dc2626]"}`}>{supportsCurrentFormat ? `当前导出格式 ${outputFormat.toUpperCase()} 可用` : `当前导出格式 ${outputFormat.toUpperCase()} 不支持该模板，将自动切换可用格式`}</div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
