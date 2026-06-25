export const dynamic = "force-dynamic";

import { RealtimePage } from "@/components/realtime/realtime-page";
import { getUploadMetadata } from "@/lib/api";

export default async function RealtimeMeetingPage() {
  const metadata = await getUploadMetadata();
  return <RealtimePage metadata={metadata} />;
}
