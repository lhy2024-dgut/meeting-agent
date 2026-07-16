"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import {
  changeCurrentUserPassword,
  getCurrentUserSmtpSettings,
  testCurrentUserSmtpSettings,
  updateCurrentUserProfile,
  updateCurrentUserSmtpSettings,
} from "@/lib/api";
import { UserSmtpSettings } from "@/types/api";

type AccountTab = "profile" | "smtp" | "password";

const TAB_OPTIONS: Array<{ key: AccountTab; label: string }> = [
  { key: "profile", label: "账户设置" },
  { key: "smtp", label: "发信设置" },
  { key: "password", label: "修改密码" },
];

function normalizeTab(value: string | null): AccountTab {
  if (value === "smtp" || value === "password") {
    return value;
  }
  return "profile";
}

export function AccountWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = useMemo(
    () => normalizeTab(searchParams.get("tab")),
    [searchParams],
  );
  const { user, refreshUser } = useAuth();

  const [displayName, setDisplayName] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");

  const [smtpSettings, setSmtpSettings] = useState<UserSmtpSettings | null>(null);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("465");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpLoading, setSmtpLoading] = useState(true);
  const [smtpSaving, setSmtpSaving] = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpError, setSmtpError] = useState("");
  const [smtpSuccess, setSmtpSuccess] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");

  useEffect(() => {
    let ignore = false;

    async function loadSmtpSettings() {
      setSmtpLoading(true);
      setSmtpError("");
      try {
        const response = await getCurrentUserSmtpSettings();
        if (ignore) return;
        setSmtpSettings(response);
        setSmtpHost(response.smtp_host);
        setSmtpPort(String(response.smtp_port || 465));
      } catch (error) {
        if (ignore) return;
        setSmtpError(error instanceof Error ? error.message : "加载发信设置失败");
      } finally {
        if (!ignore) {
          setSmtpLoading(false);
        }
      }
    }

    void loadSmtpSettings();
    return () => {
      ignore = true;
    };
  }, []);

  function switchTab(nextTab: AccountTab) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", nextTab);
    router.replace(`/account?${params.toString()}`);
  }

  async function handleProfileSave() {
    const nextDisplayName = (displayName || user?.display_name || "").trim();
    if (!nextDisplayName) {
      setProfileError("显示名称不能为空");
      setProfileSuccess("");
      return;
    }

    setProfileSaving(true);
    setProfileError("");
    setProfileSuccess("");
    try {
      await updateCurrentUserProfile({ display_name: nextDisplayName });
      await refreshUser();
      setProfileSuccess("账户信息已保存");
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : "保存账户信息失败");
    } finally {
      setProfileSaving(false);
    }
  }

  async function persistSmtpSettings(showSuccessMessage: boolean): Promise<boolean> {
    const portValue = Number(smtpPort);

    if (!smtpHost.trim()) {
      setSmtpError("SMTP 主机不能为空");
      setSmtpSuccess("");
      return false;
    }
    if (!Number.isFinite(portValue) || portValue <= 0 || portValue > 65535) {
      setSmtpError("SMTP 端口无效");
      setSmtpSuccess("");
      return false;
    }

    setSmtpSaving(true);
    setSmtpError("");
    if (showSuccessMessage) {
      setSmtpSuccess("");
    }
    try {
      const response = await updateCurrentUserSmtpSettings({
        smtp_host: smtpHost.trim(),
        smtp_port: portValue,
        smtp_password: smtpPassword,
      });
      setSmtpSettings(response);
      setSmtpHost(response.smtp_host);
      setSmtpPort(String(response.smtp_port || 465));
      setSmtpPassword("");
      await refreshUser();
      if (showSuccessMessage) {
        setSmtpSuccess("发信设置已保存");
      }
      return true;
    } catch (error) {
      setSmtpError(error instanceof Error ? error.message : "保存发信设置失败");
      return false;
    } finally {
      setSmtpSaving(false);
    }
  }

  async function handleSmtpSave() {
    void persistSmtpSettings(true);
  }

  async function handleSmtpTest() {
    setSmtpTesting(true);
    setSmtpError("");
    setSmtpSuccess("");
    try {
      const saved = await persistSmtpSettings(false);
      if (!saved) {
        return;
      }
      const response = await testCurrentUserSmtpSettings();
      if (!response.success) {
        throw new Error(response.error || "测试邮件发送失败");
      }
      setSmtpSuccess(`测试邮件已发送到 ${response.recipient_email}`);
    } catch (error) {
      setSmtpError(error instanceof Error ? error.message : "测试邮件发送失败");
    } finally {
      setSmtpTesting(false);
    }
  }

  async function handlePasswordSave() {
    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError("请填写完整的密码信息");
      setPasswordSuccess("");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("两次输入的新密码不一致");
      setPasswordSuccess("");
      return;
    }

    setPasswordSaving(true);
    setPasswordError("");
    setPasswordSuccess("");
    try {
      await changeCurrentUserPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSuccess("密码已更新");
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : "修改密码失败");
    } finally {
      setPasswordSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">账户中心</h1>
          <p className="mt-2 text-[14px] text-[var(--text-secondary)]">
            维护个人资料、发信配置和登录密码。
          </p>
        </div>
        <div className="segmented-toggle">
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={activeTab === tab.key ? "segment-active" : "segment-idle"}
              onClick={() => switchTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "profile" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,420px),1fr]">
          <div className="panel-card space-y-4">
            <div className="section-card-title !mb-1">账户设置</div>
            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                显示名称
              </label>
              <input
                className="input-shell"
                value={displayName || user?.display_name || ""}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="输入显示名称"
              />
            </div>

            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                用户名
              </label>
              <input className="input-shell" value={user?.username ?? ""} disabled />
            </div>

            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                登录邮箱
              </label>
              <input className="input-shell" value={user?.email ?? ""} disabled />
            </div>

            {profileError ? <div className="error-inline">{profileError}</div> : null}
            {profileSuccess ? <div className="info-strip">{profileSuccess}</div> : null}

            <div className="flex gap-3">
              <button
                className="primary-button"
                type="button"
                onClick={() => void handleProfileSave()}
                disabled={profileSaving}
              >
                {profileSaving ? "保存中..." : "保存账户信息"}
              </button>
            </div>
          </div>

          <div className="panel-card space-y-4">
            <div className="section-card-title !mb-1">发信状态</div>
            <div className="info-strip space-y-2">
              <div>
                当前状态：
                {user?.smtp_configured ? " 已配置个人发信" : " 未配置个人发信"}
              </div>
              {!user?.smtp_configured && smtpSettings?.using_global_fallback ? (
                <div>当前发送会议纪要时会回退使用系统全局 SMTP 配置。</div>
              ) : null}
            </div>
            <div className="flex gap-3">
              <button className="secondary-button" type="button" onClick={() => switchTab("smtp")}>
                去配置发信
              </button>
              <button className="secondary-button" type="button" onClick={() => switchTab("password")}>
                修改密码
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === "smtp" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,420px),1fr]">
          <div className="panel-card space-y-4">
            <div className="section-card-title !mb-1">发信设置</div>
            {smtpLoading ? <div className="empty-inline">加载中...</div> : null}
            {!smtpLoading ? (
              <>
                <div className="space-y-3">
                  <label className="block text-[13px] font-semibold text-[var(--dark)]">
                    发件邮箱
                  </label>
                  <input className="input-shell" value={smtpSettings?.smtp_user ?? user?.email ?? ""} disabled />
                </div>

                <div className="space-y-3">
                  <label className="block text-[13px] font-semibold text-[var(--dark)]">
                    SMTP 主机
                  </label>
                  <input
                    className="input-shell"
                    value={smtpHost}
                    onChange={(event) => setSmtpHost(event.target.value)}
                    placeholder="例如 smtp.qq.com"
                  />
                </div>

                <div className="space-y-3">
                  <label className="block text-[13px] font-semibold text-[var(--dark)]">
                    SMTP 端口
                  </label>
                  <input
                    className="input-shell"
                    value={smtpPort}
                    onChange={(event) => setSmtpPort(event.target.value)}
                    inputMode="numeric"
                    placeholder="465"
                  />
                </div>

                <div className="space-y-3">
                  <label className="block text-[13px] font-semibold text-[var(--dark)]">
                    SMTP 授权码
                  </label>
                  <input
                    className="input-shell"
                    type="password"
                    value={smtpPassword}
                    onChange={(event) => setSmtpPassword(event.target.value)}
                    placeholder={
                      smtpSettings?.smtp_password_configured
                        ? "留空则保留当前授权码"
                        : "输入邮箱授权码"
                    }
                  />
                </div>

                <div className="info-strip space-y-2">
                  <div>发件人地址默认使用当前登录邮箱。</div>
                  {smtpSettings?.using_global_fallback ? (
                    <div>当前未配置个人 SMTP，发送时会回退系统全局 SMTP。</div>
                  ) : null}
                </div>

                {smtpError ? <div className="error-inline">{smtpError}</div> : null}
                {smtpSuccess ? <div className="info-strip">{smtpSuccess}</div> : null}

                <div className="flex flex-wrap gap-3">
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => void handleSmtpSave()}
                    disabled={smtpSaving || smtpTesting}
                  >
                    {smtpSaving ? "保存中..." : "保存发信设置"}
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void handleSmtpTest()}
                    disabled={smtpSaving || smtpTesting}
                  >
                    {smtpTesting ? "测试中..." : "发送测试邮件"}
                  </button>
                </div>
              </>
            ) : null}
          </div>

          <div className="panel-card space-y-4">
            <div className="section-card-title !mb-1">使用说明</div>
            <div className="info-strip space-y-2">
              <div>1. 登录邮箱会作为默认发件邮箱，不需要额外填写 SMTP_USER 和 SMTP_FROM。</div>
              <div>2. 你只需要配置 SMTP 主机、端口和授权码。</div>
              <div>3. 保存后建议先发一封测试邮件到自己的登录邮箱，确认链路可用。</div>
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === "password" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,420px),1fr]">
          <div className="panel-card space-y-4">
            <div className="section-card-title !mb-1">修改密码</div>

            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                当前密码
              </label>
              <input
                className="input-shell"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
              />
            </div>

            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                新密码
              </label>
              <input
                className="input-shell"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>

            <div className="space-y-3">
              <label className="block text-[13px] font-semibold text-[var(--dark)]">
                确认新密码
              </label>
              <input
                className="input-shell"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                autoComplete="new-password"
              />
            </div>

            <div className="info-strip">
              新密码需要至少 8 位，并同时包含大小写字母和数字。
            </div>

            {passwordError ? <div className="error-inline">{passwordError}</div> : null}
            {passwordSuccess ? <div className="info-strip">{passwordSuccess}</div> : null}

            <div className="flex gap-3">
              <button
                className="primary-button"
                type="button"
                onClick={() => void handlePasswordSave()}
                disabled={passwordSaving}
              >
                {passwordSaving ? "提交中..." : "更新密码"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
