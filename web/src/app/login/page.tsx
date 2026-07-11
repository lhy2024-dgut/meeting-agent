import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <AuthCard mode="login" />
    </Suspense>
  );
}
