"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { isAuthPath } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/meetings/new", label: "上传" },
  { href: "/realtime", label: "实时" },
  { href: "/todos", label: "待办" },
  { href: "/chat", label: "问答" },
  { href: "/meetings", label: "历史" },
  { href: "/stats", label: "统计" },
];

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const authPage = isAuthPath(pathname);

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,var(--surface)_0%,#EFF3F8_100%)] text-[var(--text)]">
      <div className="mx-auto max-w-[1024px] px-4 pb-8 pt-6 md:px-6">
        <header className="mb-6 flex items-center justify-between border-b border-[var(--border)] pb-3">
          <Link href="/" className="text-[20px] font-extrabold tracking-[-0.02em] text-[var(--dark)]">
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
              <div className="hidden items-center gap-3 md:flex">
                <div className="text-right">
                  <div className="text-[13px] font-semibold text-[var(--dark)]">
                    {loading ? "加载中..." : user?.display_name ?? "未登录"}
                  </div>
                  <div className="text-[12px] text-[var(--muted)]">
                    {loading ? "" : user?.username ?? ""}
                  </div>
                </div>
                <button type="button" className="tertiary-button" onClick={() => void logout()}>
                  退出
                </button>
              </div>
            </div>
          ) : null}
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
