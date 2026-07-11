"use client";

import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { isAuthPath } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/meetings/new", label: "上传" },
  { href: "/realtime", label: "实时" },
  { href: "/todos", label: "待办" },
  { href: "/contacts", label: "联系人" },
  { href: "/chat", label: "问答" },
  { href: "/meetings", label: "历史" },
  { href: "/stats", label: "统计" },
];

type AppShellProps = {
  children: ReactNode;
};

type UserMenuProps = {
  loading: boolean;
  user: ReturnType<typeof useAuth>["user"];
  onLogout: () => Promise<void>;
};

function UserMenu({ loading, user, onLogout }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    window.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const displayName = loading ? "加载中..." : user?.display_name ?? "未登录";
  const email = loading ? "" : user?.email ?? "";
  const smtpStatus = user?.smtp_configured ? "个人发信已配置" : "个人发信未配置";

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        className="flex items-center gap-3 rounded-[20px] border border-[var(--border)] bg-white px-4 py-2 text-left shadow-[0_10px_24px_rgba(15,23,42,0.06)] transition hover:-translate-y-[1px]"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="hidden min-w-0 text-right sm:block">
          <div className="truncate text-[13px] font-semibold text-[var(--dark)]">{displayName}</div>
          <div className="truncate text-[12px] text-[var(--muted)]">{email}</div>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--surface)] text-[14px] font-bold text-[var(--dark)]">
          {(user?.display_name ?? user?.username ?? "U").slice(0, 1).toUpperCase()}
        </div>
      </button>

      {open ? (
        <div className="absolute right-0 z-20 mt-3 w-[260px] rounded-[24px] border border-[var(--border)] bg-white p-3 shadow-[0_18px_48px_rgba(15,23,42,0.14)]">
          <div className="rounded-[18px] bg-[var(--surface)] px-4 py-3">
            <div className="text-[14px] font-semibold text-[var(--dark)]">{displayName}</div>
            <div className="mt-1 break-all text-[12px] text-[var(--muted)]">{email}</div>
            <div className="mt-2 text-[12px] text-[var(--text-secondary)]">{smtpStatus}</div>
          </div>

          <div className="mt-3 space-y-1">
            <Link
              href="/account?tab=profile"
              className="block rounded-[14px] px-4 py-3 text-[14px] text-[var(--dark)] transition hover:bg-[var(--surface)]"
              onClick={() => setOpen(false)}
            >
              账户设置
            </Link>
            <Link
              href="/account?tab=smtp"
              className="block rounded-[14px] px-4 py-3 text-[14px] text-[var(--dark)] transition hover:bg-[var(--surface)]"
              onClick={() => setOpen(false)}
            >
              发信设置
            </Link>
            <Link
              href="/account?tab=password"
              className="block rounded-[14px] px-4 py-3 text-[14px] text-[var(--dark)] transition hover:bg-[var(--surface)]"
              onClick={() => setOpen(false)}
            >
              修改密码
            </Link>
          </div>

          <div className="mt-3 border-t border-[var(--border)] pt-3">
            <button
              type="button"
              className="block w-full rounded-[14px] px-4 py-3 text-left text-[14px] text-[#B42318] transition hover:bg-[#FFF4F2]"
              onClick={() => void onLogout()}
            >
              退出登录
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const authPage = isAuthPath(pathname);

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,var(--surface)_0%,#EFF3F8_100%)] text-[var(--text)]">
      <div className="mx-auto max-w-[1024px] px-4 pb-8 pt-6 md:px-6">
        <header className="mb-6 flex items-center justify-between border-b border-[var(--border)] pb-3">
          <Link
            href="/"
            className="text-[20px] font-extrabold tracking-[-0.02em] text-[var(--dark)]"
          >
            Meeting Agent
          </Link>
          {!authPage ? (
            <div className="flex items-center gap-4">
              <nav className="hidden items-center gap-2 md:flex">
                {NAV_ITEMS.map((item) => (
                  <Link key={item.href} href={item.href} className="nav-link">
                    {item.label}
                  </Link>
                ))}
              </nav>
              <UserMenu loading={loading} user={user} onLogout={logout} />
            </div>
          ) : null}
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
