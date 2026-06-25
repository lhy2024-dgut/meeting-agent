export const dynamic = "force-dynamic";

import { UploadPage } from "@/components/upload/upload-page";
import { getUploadMetadata } from "@/lib/api";

export default async function NewMeetingPage() {
  const metadata = await getUploadMetadata();
  return <UploadPage metadata={metadata} />;
}
