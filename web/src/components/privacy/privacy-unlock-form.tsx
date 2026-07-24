"use client";

import { FormEvent, useState } from "react";

import { unlockPrivacy } from "@/lib/api";
import { PrivacyUnlockResponse } from "@/types/api";

type PrivacyUnlockFormProps = {
  scope: "meeting" | "cross_chat_all";
  meetingId?: number;
  title: string;
  description: string;
  onUnlocked: (result: PrivacyUnlockResponse) => void | Promise<void>;
};

export function PrivacyUnlockForm({
  scope,
  meetingId,
  title,
  description,
  onUnlocked,
}: PrivacyUnlockFormProps) {
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password) {
      setError("\u8bf7\u8f93\u5165\u5f53\u524d\u8d26\u53f7\u7684\u767b\u5f55\u5bc6\u7801\u3002");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const result = await unlockPrivacy({
        scope,
        meeting_id: meetingId,
        password,
      });
      setPassword("");
      await onUnlocked(result);
    } catch (unlockError) {
      setError(
        unlockError instanceof Error
          ? unlockError.message
          : "\u89e3\u9501\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <h2 className="section-card-title !mb-1">{title}</h2>
        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{description}</p>
      </div>

      <div className="space-y-2">
        <label className="block text-[13px] font-semibold text-[var(--dark)]" htmlFor={`privacy-password-${scope}-${meetingId ?? "all"}`}>
          {"\u767b\u5f55\u5bc6\u7801"}
        </label>
        <input
          id={`privacy-password-${scope}-${meetingId ?? "all"}`}
          className="input-shell"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={submitting}
        />
      </div>

      {error ? <div className="error-inline" role="alert">{error}</div> : null}

      <button className="primary-button" type="submit" disabled={submitting}>
        {submitting ? "\u9a8c\u8bc1\u4e2d..." : "\u89e3\u9501"}
      </button>
    </form>
  );
}
