"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/cards";
import { useJobPolling } from "@/hooks/use-job-polling";
import { getAccessTokenClient } from "@/lib/auth";
import {
  ApiError,
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
  // 实时转写固定使用 FunASR paraformer-zh-streaming 流式模型，无需选择
  const asrModel = "funasr-streaming";
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
  const isRecordingRef = useRef(false);
  const cycleTimerRef = useRef<number | null>(null);
  const preferredMimeTypeRef = useRef<string | undefined>(undefined);

  // 每个分片的录制时长（毫秒）。使用「循环录制」而非 timeslice，
  // 确保每个上传的分片都是含 WebM 头、可独立解码的完整文件。
  // 用较长的分片（8s）减少分片边界处的编码断点/缺失前瞻，提升流式转写准确率。
  const CHUNK_DURATION_MS = 8000;

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

  // 用 ref 持有最新的 job，供卸载清理时读取新鲜值（避免闭包读到旧 job）
  const jobRef = useRef(job);
  useEffect(() => {
    jobRef.current = job;
  }, [job]);

  // 仅在组件真正卸载时清理会话（依赖 [apiBaseUrl]，不随 job 变化重跑，
  // 否则点击「生成会议纪要」使 job 变化时会误触发 DELETE 删掉 recording.wav）。
  useEffect(() => {
    return () => {
      isRecordingRef.current = false;
      if (cycleTimerRef.current !== null) {
        window.clearTimeout(cycleTimerRef.current);
        cycleTimerRef.current = null;
      }
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
      // 生成任务进行中/已成功时不删除：进行中会杀掉后台任务，已成功则后端已自行清理
      const currentJob = jobRef.current;
      if (currentJob && currentJob.status !== "failed") return;
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
  }, [apiBaseUrl]);

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

  function queueChunkUpload(blob: Blob) {
    if (blob.size <= 0 || !sessionIdRef.current) return;
    const chunkIndex = chunkIndexRef.current;
    chunkIndexRef.current += 1;
    setIsUploading(true);
    uploadChainRef.current = uploadChainRef.current
      .then(() => uploadChunkWithRetry(chunkIndex, blob))
      .catch((uploadError) => {
        setError(uploadError instanceof Error ? uploadError.message : "上传录音分片失败");
      })
      .finally(() => {
        setIsUploading(false);
      });
  }

  // 对同一分片带退避重试：后端对暂时性失败返回 503（需重传），超时/网络中断也应重试。
  // 后端按索引幂等去重，重传同一分片安全；分片链串行，保证录音顺序不乱。
  async function uploadChunkWithRetry(chunkIndex: number, blob: Blob) {
    const MAX_ATTEMPTS = 4;
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      const sessionId = sessionIdRef.current;
      if (!sessionId) return; // 会话已结束/清理，放弃该分片
      try {
        const formData = new FormData();
        formData.append("file", blob, `chunk_${chunkIndex}.webm`);
        formData.append("chunk_index", String(chunkIndex));
        const nextState = await uploadRealtimeChunk(sessionId, formData);
        setSession(nextState);
        return;
      } catch (uploadError) {
        const retriable =
          uploadError instanceof ApiError &&
          (uploadError.status === 503 || uploadError.isTimeout || uploadError.status === 0);
        if (!retriable || attempt === MAX_ATTEMPTS) {
          throw uploadError;
        }
        await new Promise((resolve) => setTimeout(resolve, 400 * attempt)); // 线性退避
      }
    }
  }

  // 启动一段独立录制：录满 CHUNK_DURATION_MS 后 stop()，
  // stop 会 flush 出一个含 WebM 头的完整文件；随后若仍在录音则开启下一段。
  function startRecorderCycle(stream: MediaStream) {
    const mimeType = preferredMimeTypeRef.current;
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);
    const parts: Blob[] = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) parts.push(event.data);
    };
    recorder.onstop = () => {
      if (parts.length > 0) {
        const blob = new Blob(parts, { type: recorder.mimeType || "audio/webm" });
        queueChunkUpload(blob);
      }
      if (isRecordingRef.current && streamRef.current) {
        startRecorderCycle(streamRef.current);
      }
    };

    recorderRef.current = recorder;
    recorder.start(); // 不带 timeslice：每段 stop 时产出完整可解码文件
    cycleTimerRef.current = window.setTimeout(() => {
      if (recorder.state !== "inactive") recorder.stop();
    }, CHUNK_DURATION_MS);
  }

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
      preferredMimeTypeRef.current = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : undefined;

      streamRef.current = stream;
      chunkIndexRef.current = 0;
      uploadChainRef.current = Promise.resolve();
      startedAtRef.current = Date.now();
      isRecordingRef.current = true;
      setSession(nextSession);
      setElapsedSeconds(0);
      setIsRecording(true);
      startRecorderCycle(stream);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "启动录音失败");
      isRecordingRef.current = false;
      if (cycleTimerRef.current !== null) {
        window.clearTimeout(cycleTimerRef.current);
        cycleTimerRef.current = null;
      }
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
    if (!sessionIdRef.current) return;

    setIsStopping(true);
    setError("");
    try {
      // 先阻止循环再开启新一段，然后 stop 当前录制以 flush 最后一个分片
      isRecordingRef.current = false;
      if (cycleTimerRef.current !== null) {
        window.clearTimeout(cycleTimerRef.current);
        cycleTimerRef.current = null;
      }
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        const stopPromise = new Promise<void>((resolve) => {
          recorder.addEventListener("stop", () => resolve(), { once: true });
        });
        recorder.stop();
        await stopPromise;
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
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

        <select className="input-shell w-full" value={scene} onChange={(event) => setScene(event.target.value)} disabled={Boolean(session)}>
          {metadata.scenes.map((item) => <option key={item.scene} value={item.scene}>{item.display_name}</option>)}
        </select>

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
          {session?.speaker_segments && session.speaker_segments.length > 0 ? (
            // 说话人识别后：按说话人分段显示（无时间戳）
            <div className="space-y-3">
              {session.speaker_segments.map((segment, index) => (
                <div key={index} className="rounded-[14px] bg-[var(--surface)] px-3 py-2 text-[15px] leading-7 text-[var(--text)]">
                  {segment.speaker ? (
                    <div className="mb-1 text-[12px] font-semibold text-[var(--primary)]">{segment.speaker}</div>
                  ) : null}
                  <div>{segment.text}</div>
                </div>
              ))}
            </div>
          ) : session?.transcript ? (
            // 录音中 / 停止后：一条持续增长的连续转写文本（无时间戳、不分段）
            <div className="whitespace-pre-wrap text-[15px] leading-8 text-[var(--text)]">
              {session.transcript}
            </div>
          ) : (
            <div className="text-[13px] text-[var(--muted)]">
              {isRecording ? "正在聆听，转写文字将实时显示…" : "暂无转写内容。"}
            </div>
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
