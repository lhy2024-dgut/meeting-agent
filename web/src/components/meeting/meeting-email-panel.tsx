"use client";

import { useEffect, useMemo, useState } from "react";

import { requestBrowserJson } from "@/lib/browser-api";
import { Contact, ContactGroup, EmailLog, MeetingEmailSendResponse } from "@/types/api";

type MeetingEmailPanelProps = {
  meetingId: number;
  meetingTitle: string;
  dateText: string;
};

type RecipientMode = "contacts" | "groups";

export function MeetingEmailPanel({
  meetingId,
  meetingTitle,
  dateText,
}: MeetingEmailPanelProps) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [groups, setGroups] = useState<ContactGroup[]>([]);
  const [logs, setLogs] = useState<EmailLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<MeetingEmailSendResponse | null>(null);
  const [recipientMode, setRecipientMode] = useState<RecipientMode>("contacts");
  const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([]);
  const [subject, setSubject] = useState(`【会议纪要】${meetingTitle} — ${dateText}`);
  const [attachDocument, setAttachDocument] = useState(true);
  const [documentFormat, setDocumentFormat] = useState("docx");
  const [attachHtmlSummary, setAttachHtmlSummary] = useState(false);
  const [htmlSummaryAvailable, setHtmlSummaryAvailable] = useState(false);

  useEffect(() => {
    void loadData();
    void checkHtmlSummary();
  }, [meetingId]);

  const recipients = useMemo(() => {
    if (recipientMode === "contacts") {
      return Array.from(
        new Set(
          contacts
            .filter((item) => selectedContactIds.includes(item.id))
            .map((item) => item.email.trim().toLowerCase()),
        ),
      );
    }

    return Array.from(
      new Set(
        groups
          .filter((item) => selectedGroupIds.includes(item.id))
          .flatMap((item) => item.members.map((member) => member.email.trim().toLowerCase())),
      ),
    );
  }, [contacts, groups, recipientMode, selectedContactIds, selectedGroupIds]);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [contactResponse, groupResponse, logResponse] = await Promise.all([
        requestBrowserJson<{ items: Contact[] }>("/contacts"),
        requestBrowserJson<{ items: ContactGroup[] }>("/contact-groups"),
        requestBrowserJson<{ items: EmailLog[] }>(`/meetings/${meetingId}/email-logs`),
      ]);
      setContacts(contactResponse.items);
      setGroups(groupResponse.items);
      setLogs(logResponse.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载邮件配置失败");
    } finally {
      setLoading(false);
    }
  }

  // 由父页面通过 prop 或 HtmlSummaryPanel 通知是否已生成，
  // 避免在此重复发起 html-summary 请求造成不必要的 401 噪音。
  async function checkHtmlSummary() {
    try {
      await requestBrowserJson<{ html: string }>(`/meetings/${meetingId}/html-summary`);
      setHtmlSummaryAvailable(true);
    } catch {
      setHtmlSummaryAvailable(false);
      setAttachHtmlSummary(false);
    }
  }

  async function handleSend() {
    if (!subject.trim()) {
      setError("邮件主题不能为空");
      return;
    }
    if (recipients.length === 0) {
      setError("至少选择一个收件人");
      return;
    }

    setSending(true);
    setError("");
    setResult(null);
    try {
      const response = await requestBrowserJson<MeetingEmailSendResponse>(`/meetings/${meetingId}/emails/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          recipient_emails: recipients,
          subject: subject.trim(),
          attach_minutes_document: attachDocument,
          document_format: documentFormat,
          attach_html_summary: attachHtmlSummary,
        }),
      });
      setResult(response);
      const logsResponse = await requestBrowserJson<{ items: EmailLog[] }>(`/meetings/${meetingId}/email-logs`);
      setLogs(logsResponse.items);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "邮件发送失败");
    } finally {
      setSending(false);
    }
  }

  function toggleContactId(id: number) {
    setSelectedContactIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  function toggleGroupId(id: number) {
    setSelectedGroupIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  return (
    <div className="panel-card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="section-card-title !mb-1">发送会议纪要邮件</div>
          <div className="text-[13px] text-[var(--text-secondary)]">
            从联系人或群组中选择收件人，并附带导出文档或 HTML 摘要。
          </div>
        </div>
        <div className="segmented-toggle">
          <button
            className={recipientMode === "contacts" ? "segment-active" : "segment-idle"}
            type="button"
            onClick={() => setRecipientMode("contacts")}
          >
            按联系人
          </button>
          <button
            className={recipientMode === "groups" ? "segment-active" : "segment-idle"}
            type="button"
            onClick={() => setRecipientMode("groups")}
          >
            按群组
          </button>
        </div>
      </div>

      {error ? <div className="error-inline">{error}</div> : null}

      {loading ? <div className="empty-inline">加载中...</div> : null}

      {!loading ? (
        <>
          <div className="grid gap-4 md:grid-cols-[1.4fr,1fr]">
            <div className="space-y-3">
              <div className="text-[13px] font-semibold text-[var(--text-secondary)]">收件人</div>
              {recipientMode === "contacts" ? (
                contacts.length === 0 ? (
                  <div className="text-[13px] text-[var(--muted)]">暂无联系人，请先在联系人页面添加。</div>
                ) : (
                  <div className="space-y-2 rounded-[12px] border border-[var(--border)] bg-[var(--card-bg)] p-3 max-h-[220px] overflow-y-auto">
                    {contacts.map((contact) => (
                      <label key={contact.id} className="flex items-center gap-2 cursor-pointer text-[14px] text-[var(--text)]">
                        <input
                          type="checkbox"
                          checked={selectedContactIds.includes(contact.id)}
                          onChange={() => toggleContactId(contact.id)}
                        />
                        <span className="min-w-0 truncate">
                          {contact.name} <span className="text-[var(--muted)]">&lt;{contact.email}&gt;</span>
                        </span>
                      </label>
                    ))}
                  </div>
                )
              ) : (
                groups.length === 0 ? (
                  <div className="text-[13px] text-[var(--muted)]">暂无群组，请先在联系人页面创建群组。</div>
                ) : (
                  <div className="space-y-2 rounded-[12px] border border-[var(--border)] bg-[var(--card-bg)] p-3 max-h-[220px] overflow-y-auto">
                    {groups.map((group) => (
                      <label key={group.id} className="flex items-center gap-2 cursor-pointer text-[14px] text-[var(--text)]">
                        <input
                          type="checkbox"
                          checked={selectedGroupIds.includes(group.id)}
                          onChange={() => toggleGroupId(group.id)}
                        />
                        <span className="min-w-0 truncate">
                          {group.group_name} <span className="text-[var(--muted)]">({group.members.length} 人)</span>
                        </span>
                      </label>
                    ))}
                  </div>
                )
              )}
              <div className="text-[12px] text-[var(--muted)]">
                已选择 {recipients.length} 个收件人。
              </div>
            </div>

            <div className="space-y-3">
              <div className="text-[13px] font-semibold text-[var(--text-secondary)]">附件选项</div>
              <label className="flex items-center gap-2 text-[14px] text-[var(--text)]">
                <input
                  type="checkbox"
                  checked={attachDocument}
                  onChange={(event) => setAttachDocument(event.target.checked)}
                />
                附带会议文档
              </label>
              <select
                className="input-shell"
                value={documentFormat}
                onChange={(event) => setDocumentFormat(event.target.value)}
                disabled={!attachDocument}
              >
                <option value="docx">docx</option>
                <option value="md">md</option>
                <option value="pdf">pdf</option>
              </select>
              <label className={`flex items-center gap-2 text-[14px] ${htmlSummaryAvailable ? "text-[var(--text)]" : "text-[var(--muted)]"}`}>
                <input
                  type="checkbox"
                  checked={attachHtmlSummary}
                  disabled={!htmlSummaryAvailable}
                  onChange={(event) => setAttachHtmlSummary(event.target.checked)}
                />
                附带 HTML 摘要
                {!htmlSummaryAvailable ? <span className="text-[12px]">（未生成）</span> : null}
              </label>
            </div>
          </div>

          <div className="space-y-3">
            <div className="text-[13px] font-semibold text-[var(--text-secondary)]">邮件主题</div>
            <input
              className="input-shell"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              placeholder="输入邮件主题"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button className="primary-button" type="button" disabled={sending} onClick={() => void handleSend()}>
              {sending ? "发送中..." : "发送邮件"}
            </button>
            <button className="secondary-button" type="button" onClick={() => void loadData()}>
              刷新记录
            </button>
          </div>

          {result ? (
            <div className="info-strip space-y-2">
              <div className="text-[14px] font-semibold text-[var(--dark)]">
                已完成发送：{result.success_count} 成功，{result.failure_count} 失败
              </div>
              {result.warnings.map((warning, index) => (
                <div key={`${warning}-${index}`} className="text-[13px] text-[#b45309]">
                  {warning}
                </div>
              ))}
              {result.items
                .filter((item) => !item.success)
                .map((item) => (
                  <div key={item.email} className="text-[13px] text-[#dc2626]">
                    {item.email}: {item.error}
                  </div>
                ))}
            </div>
          ) : null}

          <div className="space-y-3">
            <div className="section-card-title !mb-0">发送记录</div>
            {logs.length === 0 ? (
              <div className="text-[14px] text-[var(--muted)]">暂无发送记录。</div>
            ) : (
              logs.map((log) => (
                <div key={log.id} className="info-strip">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-[14px] font-semibold text-[var(--dark)]">
                        {log.recipient_email}
                      </div>
                      <div className="text-[12px] text-[var(--muted)]">
                        {log.sent_at ?? "未知时间"}
                      </div>
                    </div>
                    <span className={log.status === "success" ? "pill pill-info" : "pill pill-warning"}>
                      {log.status}
                    </span>
                  </div>
                  {log.error_msg ? (
                    <div className="mt-2 text-[13px] text-[#dc2626]">{log.error_msg}</div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
