"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/cards";
import { useJobPolling } from "@/hooks/use-job-polling";
import { getAccessTokenClient } from "@/lib/auth";
import {
  createRealtimeGenerateJob,
  createRealtimeSession,
  deleteRealtimeSession,
  diarizeRealtimeSession,
  getApiBaseUrl,
  stopRealtimeSession,
  uploadRealtimeChunk,
} from "@/lib/api";
import { RealtimeSessionResponse, UploadMetadataResponse } from "@/types/api";

type RealtimePageProps = {
  metadata: UploadMetadataResponse;
};

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function toIsoDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function toIsoTime(value: Date): string {
  return `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
}

function parseTerms(raw: string): string[] {
  return raw
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function RealtimePage({ metadata }: RealtimePageProps) {
  const router = useRouter();
  const now = useMemo(() => new Date(), []);
  const apiBaseUrl = getApiBaseUrl();
  const [title, setTitle] = useState("");
  const [meetingDate, setMeetingDate] = useState(toIsoDate(now));
  const [meetingTime, setMeetingTime] = useState(toIsoTime(now));
  const [outputFormat, setOutputFormat] = useState(metadata.output_formats[0] ?? "docx");
  const [scene, setScene] = useState(metadata.scenes[0]?.scene ?? "");
  const [asrModel, setAsrModel] = useState(metadata.asr_models[0] ?? "faster-whisper");
  const [terms, setTerms] = useState("");
  const [session, setSession] = useState<RealtimeSessionResponse | null>(null);
  const [error, setError] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isDiarizing, setIsDiarizing] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const uploadChainRef = useRef<Promise<void>>(Promise.resolve());
  const chunkIndexRef = useRef(0);
  const startedAtRef = useRef<number | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const { job, startPolling, resetJob } = useJobPolling({
    onSucceeded: (nextJob) => {
      if (nextJob.result?.meeting_id) {
        router.push(`/meetings/${nextJob.result.meeting_id}`);
      }
    },
    onFailed: (nextJob) => {
      setError(nextJob.error || "生成会议纪要失败");
    },
    onPollError: (pollError) => {
      setError(pollError.message);
    },
  });

  useEffect(() => {
    sessionIdRef.current = session?.session_id ?? null;
  }, [session]);

  useEffect(() => {
    return () => {
      try {
        if (recorderRef.current && recorderRef.current.state !== "inactive") {
          recorderRef.current.stop();
        }
      } catch {
        // Ignore teardown race during route transitions.
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      const sessionId = sessionIdRef.current;
      if (!sessionId) return;
      if (job && job.status !== "failed" && job.status !== "succeeded") return;
      const accessToken = getAccessTokenClient();
      void fetch(`${apiBaseUrl}/realtime/sessions/${sessionId}`, {
        method: "DELETE",
        headers: accessToken
          ? {
              Authorization: `Bearer ${accessToken}`,
            }
          : undefined,
        keepalive: true,
      }).catch(() => undefined);
    };
  }, [apiBaseUrl, job]);

  useEffect(() => {
    if (!isRecording) {
      setElapsedSeconds(session?.duration_seconds ?? 0);
      return;
    }

    const timer = window.setInterval(() => {
      if (!startedAtRef.current) return;
      const liveSeconds = (Date.now() - startedAtRef.current) / 1000;
      setElapsedSeconds(Math.max(session?.duration_seconds ?? 0, liveSeconds));
    }, 500);
    return () => window.clearInterval(timer);
  }, [isRecording, session?.duration_seconds]);

  async function handleStartRecording() {
    setError("");
    setIsStarting(true);
    try {
      const nextSession = await createRealtimeSession({
        title,
        meeting_date: meetingDate,
        meeting_time: meetingTime,
        output_format: outputFormat,
        scene,
        asr_model: asrModel,
        terms: parseTerms(terms),
      });
      sessionIdRef.current = nextSession.session_id;

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : undefined;
      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        if (event.data.size <= 0 || !sessionIdRef.current) return;
        const chunkIndex = chunkIndexRef.current;
        chunkIndexRef.current += 1;
        setIsUploading(true);
        uploadChainRef.current = uploadChainRef.current
          .then(async () => {
            const formData = new FormData();
            formData.append("file", event.data, `chunk_${chunkIndex}.webm`);
            formData.append("chunk_index", String(chunkIndex));
            const nextState = await uploadRealtimeChunk(sessionIdRef.current!, formData);
            setSession(nextState);
          })
          .catch((uploadError) => {
            setError(uploadError instanceof Error ? uploadError.message : "上传录音分片失败");
          })
          .finally(() => {
            setIsUploading(false);
          });
      };

      recorderRef.current = recorder;
      streamRef.current = stream;
      chunkIndexRef.current = 0;
      startedAtRef.current = Date.now();
      setSession(nextSession);
      setElapsedSeconds(0);
      setIsRecording(true);
      recorder.start(3000);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "启动录音失败");
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      if (sessionIdRef.current) {
        void deleteRealtimeSession(sessionIdRef.current).catch(() => undefined);
        sessionIdRef.current = null;
      }
    } finally {
      setIsStarting(false);
    }
  }

  async function handleStopRecording() {
    const recorder = recorderRef.current;
    if (!recorder || !sessionIdRef.current) return;

    setIsStopping(true);
    setError("");
    try {
      const stopPromise = new Promise<void>((resolve) => {
        recorder.addEventListener("stop", () => resolve(), { once: true });
      });
      recorder.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      await stopPromise;
      await uploadChainRef.current;
      const nextSession = await stopRealtimeSession(sessionIdRef.current);
      setSession(nextSession);
      setIsRecording(false);
      recorderRef.current = null;
      streamRef.current = null;
      startedAtRef.current = null;
      setElapsedSeconds(nextSession.duration_seconds);
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : "停止录音失败");
    } finally {
      setIsStopping(false);
    }
  }

  async function handleDiarize() {
    if (!session) return;
    setIsDiarizing(true);
    setError("");
    try {
      const nextSession = await diarizeRealtimeSession(session.session_id);
      setSession(nextSession);
    } catch (diarizeError) {
      setError(diarizeError instanceof Error ? diarizeError.message : "说话人识别失败");
    } finally {
      setIsDiarizing(false);
    }
  }

  async function handleGenerate() {
    if (!session) return;
    setError("");
    try {
      const created = await createRealtimeGenerateJob(session.session_id);
      const initialJob = await startPolling(created.job_id);
      if (initialJob.status === "failed") {
        setError(initialJob.error || "生成会议纪要失败");
      }
      if (initialJob.status === "succeeded" && initialJob.result?.meeting_id) {
        router.push(`/meetings/${initialJob.result.meeting_id}`);
      }
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "创建生成任务失败");
    }
  }

  function handleReset() {
    const currentSessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    setSession(null);
    setError("");
    setIsRecording(false);
    setElapsedSeconds(0);
    resetJob();
    if (currentSessionId) {
      void deleteRealtimeSession(currentSessionId).catch(() => undefined);
    }
  }

  const visibleSegments = session?.speaker_segments.length
    ? session.speaker_segments
    : session?.segments ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">{"实时转写"}</h1>
        <div className="text-[14px] text-[var(--text-secondary)]">{"用浏览器直接录音，边录边转写，结束后可生成会议纪要。"}</div>
      </div>

      <Card className="space-y-5">
        <div className="grid gap-4 md:grid-cols-3">
          <input className="input-shell md:col-span-3" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="会议标题（可选）" disabled={Boolean(session)} />
          <input className="input-shell" type="date" value={meetingDate} onChange={(event) => setMeetingDate(event.target.value)} disabled={Boolean(session)} />
          <input className="input-shell" type="time" value={meetingTime} onChange={(event) => setMeetingTime(event.target.value)} disabled={Boolean(session)} />
          <select className="input-shell" value={outputFormat} onChange={(event) => setOutputFormat(event.target.value)} disabled={Boolean(session)}>
            {metadata.output_formats.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <select className="input-shell" value={scene} onChange={(event) => setScene(event.target.value)} disabled={Boolean(session)}>
            {metadata.scenes.map((item) => <option key={item.scene} value={item.scene}>{item.display_name}</option>)}
          </select>
          <select className="input-shell" value={asrModel} onChange={(event) => setAsrModel(event.target.value)} disabled={Boolean(session)}>
            {metadata.asr_models.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>

        <textarea className="input-shell min-h-[120px]" value={terms} onChange={(event) => setTerms(event.target.value)} placeholder="术语词表（每行一个，可选）" disabled={Boolean(session)} />

        <div className="flex flex-wrap items-center gap-3">
          {!isRecording ? (
            <button className="primary-button" type="button" onClick={handleStartRecording} disabled={isStarting || Boolean(session)}>
              {isStarting ? "启动中..." : "开始录音"}
            </button>
          ) : (
            <button className="primary-button" type="button" onClick={handleStopRecording} disabled={isStopping}>
              {isStopping ? "停止中..." : "结束录音"}
            </button>
          )}
          <div className="rounded-full bg-[#fef2f2] px-4 py-2 text-[14px] font-semibold text-[#dc2626]">
            {isRecording ? "录音中" : "待录音"} · {formatDuration(elapsedSeconds)}
          </div>
          {isUploading ? <div className="text-[13px] text-[var(--muted)]">{"上传并转写最新分片中..."}</div> : null}
        </div>
      </Card>

      {error ? <div className="error-inline">{error}</div> : null}

      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="section-card-title !mb-1">{"转写结果"}</h2>
            <div className="text-[13px] text-[var(--text-secondary)]">{session?.message || "录音开始后，这里会持续追加转写内容。"}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {session && !isRecording ? (
              <button className="secondary-button" type="button" onClick={handleDiarize} disabled={isDiarizing}>
                {isDiarizing ? "识别中..." : "说话人识别"}
              </button>
            ) : null}
            {session && !isRecording ? (
              <button className="primary-button" type="button" onClick={handleGenerate}>
                {"生成会议纪要"}
              </button>
            ) : null}
            {session && !isRecording ? (
              <button className="tertiary-button" type="button" onClick={handleReset}>
                {"重新开始"}
              </button>
            ) : null}
          </div>
        </div>

        <div className="rounded-[18px] border border-[var(--border)] bg-white p-4">
          {visibleSegments.length > 0 ? (
            <div className="space-y-3">
              {visibleSegments.map((segment, index) => (
                <div key={`${segment.timestamp}-${index}`} className="rounded-[14px] bg-[var(--surface)] px-3 py-2 text-[14px] leading-7 text-[var(--text)]">
                  <div className="mb-1 text-[12px] font-semibold text-[var(--primary)]">
                    {formatDuration(segment.start)}
                    {segment.speaker ? ` · ${segment.speaker}` : ""}
                  </div>
                  <div>{segment.text}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[13px] text-[var(--muted)]">{"暂无转写内容。"}</div>
          )}
        </div>
      </Card>

      {job ? (
        <Card className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-[16px] font-bold text-[var(--dark)]">{"生成进度"}</div>
              <div className="text-[13px] text-[var(--text-secondary)]">{job.message}</div>
            </div>
            <div className="text-[14px] font-semibold text-[var(--primary)]">{job.progress_pct}%</div>
          </div>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${job.progress_pct}%` }} /></div>
          <div className="text-[12px] text-[var(--muted)]">{"状态："}{job.status}{" / 阶段："}{job.stage}</div>
        </Card>
      ) : null}
    </div>
  );
}
