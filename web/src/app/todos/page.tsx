export const dynamic = "force-dynamic";

import { TodoWorkspace } from "@/components/todos/todo-workspace";
import { getMeetings, getTodos } from "@/lib/api";

export default async function TodosPage() {
  const [todos, firstMeetingsPage] = await Promise.all([
    getTodos({ includeCancelled: true }),
    getMeetings({ page: 0, pageSize: 50 }),
  ]);
  const remainingPages = await Promise.all(
    Array.from(
      { length: Math.max(firstMeetingsPage.total_pages - 1, 0) },
      (_, index) => getMeetings({ page: index + 1, pageSize: 50 }),
    ),
  );
  const meetings = [
    ...firstMeetingsPage.items,
    ...remainingPages.flatMap((page) => page.items),
  ];

  return <TodoWorkspace initialTodos={todos.items} meetings={meetings} title="我的待办" />;
}
