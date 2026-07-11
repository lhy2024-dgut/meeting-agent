export const dynamic = "force-dynamic";

import { ChatWorkspace } from "@/components/chat";
import { getMeetings } from "@/lib/api";

export default async function ChatPage() {
  const meetings = await getMeetings({ page: 0, pageSize: 50 });

  return <ChatWorkspace meetings={meetings.items} />;
}
