"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

import { Card, EmptyState } from "@/components/ui/cards";
import { Pill } from "@/components/ui/pills";
import { deleteMeeting, updateMeetingProjectName } from "@/lib/api";
import { formatMeetingListDate } from "@/lib/format";
import { MeetingListResponse, MeetingSummary } from "@/types/api";

type HistoryPageProps = {
  data: MeetingListResponse;
  filters: { search: string; duration: string; environment: string };
};

const DURATION_OPTIONS = [
  { value: "", label: "\u5168\u90e8\u65f6\u957f" },
  { value: "short", label: "\u77ed\u4f1a (<5min)" },
  { value: "medium", label: "\u4e2d\u7b49 (5-30min)" },
  { value: "long", label: "\u957f\u4f1a (>30min)" },
];

const ENVIRONMENT_OPTIONS = [
  { value: "", label: "\u5168\u90e8\u73af\u5883" },
  { value: "quiet", label: "\u5b89\u9759" },
  { value: "noisy", label: "\u5624\u6742" },
  { value: "multi_speaker", label: "\u591a\u4eba" },
];

export function HistoryPage({ data, filters }: HistoryPageProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [search, setSearch] = useState(filters.search);
  const [duration, setDuration] = useState(filters.duration);
  const [environment, setEnvironment] = useState(filters.environment);

  function buildMeetingsUrl(next: { page?: number; search?: string; duration?: string; environment?: string }) {
    const searchParams = new URLSearchParams();
    const page = next.page ?? 0;
    const nextSearch = next.search ?? search;
    const nextDuration = next.duration ?? duration;
    const nextEnvironment = next.environment ?? environment;
    if (page > 0) searchParams.set("page", String(page));
    if (nextSearch.trim()) searchParams.set("search", nextSearch.trim());
    if (nextDuration) searchParams.set("duration", nextDuration);
    if (nextEnvironment) searchParams.set("environment", nextEnvironment);
    const query = searchParams.toString();
    return `/meetings${query ? `?${query}` : ""}`;
  }

  function applyFilters(next?: { search?: string; duration?: string; environment?: string }) {
    startTransition(() => {
      router.push(buildMeetingsUrl({ page: 0, search: next?.search, duration: next?.duration, environment: next?.environment }));
    });
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyFilters();
  }

  return (
    <div className="space-y-5">
      <div><h1 className="page-title">{"\u5386\u53f2\u4f1a\u8bae"}</h1></div>

      <FilterBar
        search={search}
        duration={duration}
        environment={environment}
        isPending={isPending}
        onSearchChange={setSearch}
        onDurationChange={(value) => { setDuration(value); applyFilters({ duration: value }); }}
        onEnvironmentChange={(value) => { setEnvironment(value); applyFilters({ environment: value }); }}
        onSubmit={onSubmit}
      />

      {data.total === 0 ? (
        <EmptyState icon="-" title={"\u6682\u65e0\u4f1a\u8bae\u8bb0\u5f55"} description={"\u4e0a\u4f20\u5e76\u5904\u7406\u7b2c\u4e00\u573a\u4f1a\u8bae\u540e\uff0c\u8fd9\u91cc\u4f1a\u663e\u793a\u6240\u6709\u5386\u53f2\u8bb0\u5f55\u3002"} />
      ) : (
        <>
          <div className="text-[12px] text-[var(--muted)]">{"\u5171"} {data.total} {"\u573a\u4f1a\u8bae / \u7b2c"} {data.page + 1} / {data.total_pages} {"\u9875"}{isPending ? " / \u7b5b\u9009\u4e2d..." : ""}</div>
          <div className="space-y-4">{data.items.map((meeting) => <MeetingHistoryCard key={meeting.id} meeting={meeting} />)}</div>
          {data.total_pages > 1 ? (
            <div className="grid grid-cols-3 items-center gap-4">
              <div>{data.page > 0 ? <Link href={buildMeetingsUrl({ page: data.page - 1 })} className="secondary-link">{"\u4e0a\u4e00\u9875"}</Link> : null}</div>
              <div className="text-center text-[14px] text-[var(--text-secondary)]">{data.page + 1} / {data.total_pages}</div>
              <div className="text-right">{data.page + 1 < data.total_pages ? <Link href={buildMeetingsUrl({ page: data.page + 1 })} className="secondary-link">{"\u4e0b\u4e00\u9875"}</Link> : null}</div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

type MeetingHistoryCardProps = { meeting: MeetingSummary };

function MeetingHistoryCard({ meeting }: MeetingHistoryCardProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [isEditingProject, setIsEditingProject] = useState(false);
  const [projectName, setProjectName] = useState(meeting.project_name || "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");

  async function handleProjectSave() {
    try {
      setError("");
      await updateMeetingProjectName(meeting.id, projectName.trim());
      setIsEditingProject(false);
      startTransition(() => router.refresh());
    } catch (projectError) {
      setError(projectError instanceof Error ? projectError.message : "\u9879\u76ee\u540d\u4fdd\u5b58\u5931\u8d25");
    }
  }

  async function handleDelete() {
    try {
      setError("");
      await deleteMeeting(meeting.id);
      startTransition(() => router.refresh());
      setConfirmDelete(false);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "\u5220\u9664\u4f1a\u8bae\u5931\u8d25");
    }
  }

  return (
    <Card>
      <div className="grid gap-4 md:grid-cols-[3fr_1fr]">
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
            <div>
              <div className="text-[16px] font-bold text-[var(--dark)]">{meeting.title || "\u672a\u547d\u540d\u4f1a\u8bae"}</div>
              <div className="mt-1 text-[12px] text-[var(--muted)]">{formatMeetingListDate(meeting.created_at)} / {meeting.duration_label} / {meeting.environment_label}</div>
            </div>
            <div className="md:text-right">
              {isEditingProject ? (
                <div className="space-y-2">
                  <input className="input-shell" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder={"\u8f93\u5165\u9879\u76ee\u540d..."} />
                  <div className="flex justify-end gap-2">
                    <button className="secondary-button" type="button" disabled={isPending} onClick={() => { setIsEditingProject(false); setProjectName(meeting.project_name || ""); }}>{"\u53d6\u6d88"}</button>
                    <button className="primary-button" type="button" disabled={isPending} onClick={() => void handleProjectSave()}>{"\u4fdd\u5b58"}</button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-end gap-2">
                  <Pill variant={meeting.project_name ? "project" : "muted"}>{meeting.project_name || "\u672a\u5206\u7c7b"}</Pill>
                  <button className="tertiary-link" type="button" onClick={() => setIsEditingProject(true)}>{"\u7f16\u8f91"}</button>
                </div>
              )}
            </div>
          </div>
          {meeting.short_summary ? <div className="text-[13px] leading-[1.5] text-[var(--text-secondary)]">{meeting.short_summary}</div> : null}
          <div className="flex flex-wrap gap-2">
            <Pill variant="warning">{meeting.action_item_count} {"\u5f85\u529e"}</Pill>
            <Pill variant="info">{meeting.resolution_count} {"\u51b3\u8bae"}</Pill>
          </div>
          {error ? <div className="error-inline">{error}</div> : null}
        </div>

        <div className="flex flex-wrap items-start justify-end gap-2">
          <Link href={`/meetings/${meeting.id}`} className="primary-link">{"\u67e5\u770b"}</Link>
          {confirmDelete ? (
            <button className="danger-button" type="button" disabled={isPending} onClick={() => void handleDelete()}>{"\u786e\u8ba4\u5220\u9664"}</button>
          ) : (
            <button className="secondary-button" type="button" onClick={() => { setError(""); setConfirmDelete(true); }}>{"\u5220\u9664"}</button>
          )}
          {confirmDelete ? <div className="text-[12px] text-[var(--muted)]">{"\u518d\u6b21\u70b9\u51fb\u4ee5\u786e\u8ba4\u5220\u9664"}</div> : null}
        </div>
      </div>
    </Card>
  );
}

type FilterBarProps = {
  search: string;
  duration: string;
  environment: string;
  isPending: boolean;
  onSearchChange: (value: string) => void;
  onDurationChange: (value: string) => void;
  onEnvironmentChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

function FilterBar({ search, duration, environment, isPending, onSearchChange, onDurationChange, onEnvironmentChange, onSubmit }: FilterBarProps) {
  return (
    <form className="grid gap-3 md:grid-cols-[2fr_1fr_1fr_auto]" onSubmit={onSubmit}>
      <input className="input-shell" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder={"\u641c\u7d22\u6807\u9898 / \u6458\u8981 / \u9879\u76ee\u540d..."} />
      <select className="input-shell" value={duration} onChange={(event) => onDurationChange(event.target.value)}>{DURATION_OPTIONS.map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}</select>
      <select className="input-shell" value={environment} onChange={(event) => onEnvironmentChange(event.target.value)}>{ENVIRONMENT_OPTIONS.map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}</select>
      <button className="primary-button" type="submit" disabled={isPending}>{isPending ? "\u7b5b\u9009\u4e2d..." : "\u641c\u7d22"}</button>
    </form>
  );
}
