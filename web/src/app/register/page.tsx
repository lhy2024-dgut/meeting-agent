import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <AuthCard mode="register" />
    </Suspense>
  );
}
