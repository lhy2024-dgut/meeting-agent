import { Suspense } from "react";

import { AccountWorkspace } from "@/components/account/account-workspace";

export default function AccountPage() {
  return (
    <Suspense fallback={null}>
      <AccountWorkspace />
    </Suspense>
  );
}
