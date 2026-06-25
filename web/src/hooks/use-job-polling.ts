"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getJob } from "@/lib/api";
import { JobStatusResponse } from "@/types/api";

type UseJobPollingOptions = {
  intervalMs?: number;
  onSucceeded?: (job: JobStatusResponse) => void;
  onFailed?: (job: JobStatusResponse) => void;
  onPollError?: (error: ApiError) => void;
};

const DEFAULT_INTERVAL_MS = 1500;

export function useJobPolling(options: UseJobPollingOptions = {}) {
  const { intervalMs = DEFAULT_INTERVAL_MS, onSucceeded, onFailed, onPollError } = options;
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const callbacksRef = useRef({ onSucceeded, onFailed, onPollError });

  useEffect(() => {
    callbacksRef.current = { onSucceeded, onFailed, onPollError };
  }, [onSucceeded, onFailed, onPollError]);

  useEffect(() => {
    if (!job || job.status === "failed" || job.status === "succeeded") {
      return;
    }

    let active = true;
    let timer: number | null = null;
    let controller: AbortController | null = null;

    const poll = async () => {
      controller = new AbortController();
      try {
        const nextJob = await getJob(job.job_id, { signal: controller.signal });
        if (!active) {
          return;
        }
        setJob(nextJob);
        if (nextJob.status === "succeeded") {
          callbacksRef.current.onSucceeded?.(nextJob);
          return;
        }
        if (nextJob.status === "failed") {
          callbacksRef.current.onFailed?.(nextJob);
          return;
        }
      } catch (error) {
        if (!active) {
          return;
        }
        const normalized =
          error instanceof ApiError
            ? error
            : new ApiError({
                message: error instanceof Error ? error.message : "查询任务状态失败",
              });
        callbacksRef.current.onPollError?.(normalized);
        return;
      }

      timer = window.setTimeout(() => {
        void poll();
      }, intervalMs);
    };

    timer = window.setTimeout(() => {
      void poll();
    }, intervalMs);

    return () => {
      active = false;
      if (timer !== null) {
        window.clearTimeout(timer);
      }
      controller?.abort();
    };
  }, [intervalMs, job]);

  const startPolling = useCallback(async (jobId: string) => {
    const initialJob = await getJob(jobId);
    setJob(initialJob);
    return initialJob;
  }, []);

  const resetJob = useCallback(() => {
    setJob(null);
  }, []);

  return {
    job,
    setJob,
    startPolling,
    resetJob,
  };
}