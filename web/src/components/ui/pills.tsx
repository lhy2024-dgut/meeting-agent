import { ReactNode } from "react";

type PillProps = {
  children: ReactNode;
  variant?: "warning" | "info" | "project" | "muted";
};

export function Pill({ children, variant = "muted" }: PillProps) {
  const variantClass = {
    warning: "pill-warning",
    info: "pill-info",
    project: "pill-project",
    muted: "pill-muted",
  }[variant];

  return <span className={`pill ${variantClass}`}>{children}</span>;
}
