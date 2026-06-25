"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { Card } from "@/components/ui/cards";

type AuthMode = "login" | "register";

type AuthCardProps = {
  mode: AuthMode;
};

export function AuthCard({ mode }: AuthCardProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register } = useAuth();
  const nextPath = searchParams.get("next") || "/";

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const title = mode === "login" ? "登录" : "注册";
  const description = useMemo(
    () =>
      mode === "login"
        ? "使用你的用户名或邮箱登录后继续访问会议数据。"
        : "创建本地账号后，会议、待办和实时录音数据会按用户隔离。",
    [mode],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (mode === "login") {
        await login({ login: username.trim(), password });
      } else {
        await register({
          username: username.trim(),
          email: email.trim(),
          password,
          display_name: displayName.trim() || username.trim(),
        });
      }
      router.replace(nextPath);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "认证失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-[460px]">
      <Card className="auth-card">
        <div className="space-y-2">
          <div className="auth-card-eyebrow">Meeting Agent</div>
          <h1 className="page-title !mb-0">{title}</h1>
          <p className="text-[14px] leading-6 text-[var(--text-secondary)]">
            {description}
          </p>
        </div>

        <form className="mt-6 space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          <div className="space-y-2">
            <label className="auth-label" htmlFor="auth-username">
              用户名{mode === "login" ? " / 邮箱" : ""}
            </label>
            <input
              id="auth-username"
              className="input-shell"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={mode === "login" ? "输入用户名或邮箱" : "输入用户名"}
              autoComplete="username"
              required
            />
          </div>

          {mode === "register" ? (
            <>
              <div className="space-y-2">
                <label className="auth-label" htmlFor="auth-email">
                  邮箱
                </label>
                <input
                  id="auth-email"
                  className="input-shell"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="输入邮箱"
                  autoComplete="email"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="auth-label" htmlFor="auth-display-name">
                  显示名
                </label>
                <input
                  id="auth-display-name"
                  className="input-shell"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="输入显示名（可选）"
                />
              </div>
            </>
          ) : null}

          <div className="space-y-2">
            <label className="auth-label" htmlFor="auth-password">
              密码
            </label>
            <input
              id="auth-password"
              className="input-shell"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="输入密码"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </div>

          {mode === "register" ? (
            <div className="text-[12px] text-[var(--muted)]">
              密码至少 8 位，并包含大小写字母和数字。
            </div>
          ) : null}

          {error ? <div className="error-inline">{error}</div> : null}

          <button className="primary-button w-full" type="submit" disabled={loading}>
            {loading ? "提交中..." : title}
          </button>
        </form>

        <div className="mt-5 text-[13px] text-[var(--text-secondary)]">
          {mode === "login" ? (
            <>
              还没有账号？{" "}
              <Link className="secondary-link-inline" href="/register">
                去注册
              </Link>
            </>
          ) : (
            <>
              已有账号？{" "}
              <Link className="secondary-link-inline" href="/login">
                去登录
              </Link>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
