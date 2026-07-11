"use client";

import { useEffect, useMemo, useState } from "react";

import { requestBrowserJson } from "@/lib/browser-api";
import { Contact, ContactGroup } from "@/types/api";

type TabKey = "contacts" | "groups";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const EMPTY_CONTACT_FORM = {
  id: 0,
  name: "",
  email: "",
  note: "",
  groupIds: [] as number[],
};

const EMPTY_GROUP_FORM = {
  id: 0,
  groupName: "",
  memberIds: [] as number[],
};

export function ContactsWorkspace({
  initialContacts = [],
  initialGroups = [],
}: {
  initialContacts?: Contact[];
  initialGroups?: ContactGroup[];
}) {
  const [tab, setTab] = useState<TabKey>("contacts");
  const [contacts, setContacts] = useState<Contact[]>(initialContacts);
  const [groups, setGroups] = useState<ContactGroup[]>(initialGroups);
  const [loading, setLoading] = useState(initialContacts.length === 0 && initialGroups.length === 0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [contactForm, setContactForm] = useState(EMPTY_CONTACT_FORM);
  const [groupForm, setGroupForm] = useState(EMPTY_GROUP_FORM);

  const contactOptions = useMemo(
    () => contacts.map((item) => ({ value: item.id, label: `${item.name} <${item.email}>` })),
    [contacts],
  );

  useEffect(() => {
    void loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const contactResponse = await requestBrowserJson<{ items: Contact[] }>("/contacts");
      const groupResponse = await requestBrowserJson<{ items: ContactGroup[] }>("/contact-groups");
      setContacts(contactResponse.items);
      setGroups(groupResponse.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载联系人失败");
    } finally {
      setLoading(false);
    }
  }

  function startEditContact(contact: Contact) {
    setTab("contacts");
    setContactForm({
      id: contact.id,
      name: contact.name,
      email: contact.email,
      note: contact.note ?? "",
      groupIds: contact.groups.map((item) => item.id),
    });
  }

  function startEditGroup(group: ContactGroup) {
    setTab("groups");
    setGroupForm({
      id: group.id,
      groupName: group.group_name,
      memberIds: group.members.map((item) => item.id),
    });
  }

  async function submitContactForm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contactForm.name.trim()) {
      setError("联系人姓名不能为空");
      return;
    }
    if (!EMAIL_PATTERN.test(contactForm.email.trim().toLowerCase())) {
      setError("联系人邮箱格式不正确");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        name: contactForm.name.trim(),
        email: contactForm.email.trim().toLowerCase(),
        note: contactForm.note.trim(),
        group_ids: contactForm.groupIds,
      };
      if (contactForm.id) {
        await requestBrowserJson<Contact>(`/contacts/${contactForm.id}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      } else {
        await requestBrowserJson<Contact>("/contacts", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      }
      setContactForm(EMPTY_CONTACT_FORM);
      await loadData();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "联系人保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function submitGroupForm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!groupForm.groupName.trim()) {
      setError("群组名称不能为空");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        group_name: groupForm.groupName.trim(),
        member_ids: groupForm.memberIds,
      };
      if (groupForm.id) {
        await requestBrowserJson<ContactGroup>(`/contact-groups/${groupForm.id}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      } else {
        await requestBrowserJson<ContactGroup>("/contact-groups", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
      }
      setGroupForm(EMPTY_GROUP_FORM);
      await loadData();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "群组保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeContact(contactId: number) {
    if (!window.confirm("确认删除这个联系人？")) {
      return;
    }
    setError("");
    try {
      await requestBrowserJson<{ success: boolean }>(`/contacts/${contactId}`, {
        method: "DELETE",
      });
      if (contactForm.id === contactId) {
        setContactForm(EMPTY_CONTACT_FORM);
      }
      await loadData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "联系人删除失败");
    }
  }

  async function removeGroup(groupId: number) {
    if (!window.confirm("确认删除这个群组？")) {
      return;
    }
    setError("");
    try {
      await requestBrowserJson<{ success: boolean }>(`/contact-groups/${groupId}`, {
        method: "DELETE",
      });
      if (groupForm.id === groupId) {
        setGroupForm(EMPTY_GROUP_FORM);
      }
      await loadData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "群组删除失败");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="page-title">联系人</h1>
          <p className="mt-2 text-[14px] text-[var(--text-secondary)]">
            管理邮件联系人和发送群组，供会议纪要邮件分发使用。
          </p>
        </div>
        <div className="segmented-toggle">
          <button
            className={tab === "contacts" ? "segment-active" : "segment-idle"}
            type="button"
            onClick={() => setTab("contacts")}
          >
            联系人
          </button>
          <button
            className={tab === "groups" ? "segment-active" : "segment-idle"}
            type="button"
            onClick={() => setTab("groups")}
          >
            群组
          </button>
        </div>
      </div>

      {error ? <div className="error-inline">{error}</div> : null}

      {tab === "contacts" ? (
        <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
          <div className="panel-card">
            <div className="section-card-title">
              {contactForm.id ? "编辑联系人" : "新建联系人"}
            </div>
            <form className="space-y-3" onSubmit={(event) => void submitContactForm(event)}>
              <input
                className="input-shell"
                value={contactForm.name}
                onChange={(event) =>
                  setContactForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="姓名"
              />
              <input
                className="input-shell"
                value={contactForm.email}
                onChange={(event) =>
                  setContactForm((current) => ({ ...current, email: event.target.value }))
                }
                placeholder="邮箱"
              />
              <input
                className="input-shell"
                value={contactForm.note}
                onChange={(event) =>
                  setContactForm((current) => ({ ...current, note: event.target.value }))
                }
                placeholder="备注"
              />
              <select
                multiple
                className="input-shell min-h-[140px]"
                value={contactForm.groupIds.map(String)}
                onChange={(event) => {
                  const values = Array.from(event.target.selectedOptions).map((item) => Number(item.value));
                  setContactForm((current) => ({ ...current, groupIds: values }));
                }}
              >
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.group_name}
                  </option>
                ))}
              </select>
              <div className="text-[12px] text-[var(--muted)]">
                按住 `Ctrl` 或 `Cmd` 可多选所属群组。
              </div>
              <div className="flex gap-3">
                <button className="primary-button" type="submit" disabled={saving}>
                  {saving ? "保存中..." : contactForm.id ? "保存联系人" : "创建联系人"}
                </button>
                {contactForm.id ? (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setContactForm(EMPTY_CONTACT_FORM)}
                  >
                    取消编辑
                  </button>
                ) : null}
              </div>
            </form>
          </div>

          <div className="space-y-4">
            {loading ? <div className="empty-inline">加载中...</div> : null}
            {!loading && contacts.length === 0 ? (
              <div className="panel-card text-[14px] text-[var(--muted)]">暂无联系人。</div>
            ) : null}
            {contacts.map((contact) => (
              <div key={contact.id} className="panel-card">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-2">
                    <div className="text-[18px] font-bold text-[var(--dark)]">{contact.name}</div>
                    <div className="text-[14px] text-[var(--text-secondary)]">{contact.email}</div>
                    {contact.note ? (
                      <div className="text-[13px] text-[var(--muted)]">{contact.note}</div>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      {contact.groups.length === 0 ? (
                        <span className="pill pill-muted">未分组</span>
                      ) : (
                        contact.groups.map((group) => (
                          <span key={group.id} className="pill pill-project">
                            {group.group_name}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => startEditContact(contact)}
                    >
                      编辑
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void removeContact(contact.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
          <div className="panel-card">
            <div className="section-card-title">
              {groupForm.id ? "编辑群组" : "新建群组"}
            </div>
            <form className="space-y-3" onSubmit={(event) => void submitGroupForm(event)}>
              <input
                className="input-shell"
                value={groupForm.groupName}
                onChange={(event) =>
                  setGroupForm((current) => ({ ...current, groupName: event.target.value }))
                }
                placeholder="群组名称"
              />
              <select
                multiple
                className="input-shell min-h-[180px]"
                value={groupForm.memberIds.map(String)}
                onChange={(event) => {
                  const values = Array.from(event.target.selectedOptions).map((item) => Number(item.value));
                  setGroupForm((current) => ({ ...current, memberIds: values }));
                }}
              >
                {contactOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="text-[12px] text-[var(--muted)]">
                群组成员来自联系人列表。
              </div>
              <div className="flex gap-3">
                <button className="primary-button" type="submit" disabled={saving}>
                  {saving ? "保存中..." : groupForm.id ? "保存群组" : "创建群组"}
                </button>
                {groupForm.id ? (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setGroupForm(EMPTY_GROUP_FORM)}
                  >
                    取消编辑
                  </button>
                ) : null}
              </div>
            </form>
          </div>

          <div className="space-y-4">
            {loading ? <div className="empty-inline">加载中...</div> : null}
            {!loading && groups.length === 0 ? (
              <div className="panel-card text-[14px] text-[var(--muted)]">暂无群组。</div>
            ) : null}
            {groups.map((group) => (
              <div key={group.id} className="panel-card">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-2">
                    <div className="text-[18px] font-bold text-[var(--dark)]">{group.group_name}</div>
                    <div className="text-[13px] text-[var(--muted)]">
                      {group.members.length} 位成员
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {group.members.length === 0 ? (
                        <span className="pill pill-muted">暂无成员</span>
                      ) : (
                        group.members.map((member) => (
                          <span key={member.id} className="pill pill-info">
                            {member.name}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => startEditGroup(group)}
                    >
                      编辑
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void removeGroup(group.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
