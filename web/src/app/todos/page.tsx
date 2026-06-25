export const dynamic = "force-dynamic";

import { TodoWorkspace } from "@/components/todos/todo-workspace";
import { getMeetings, getTodos } from "@/lib/api";

export default async function TodosPage() {
  const [todos, meetings] = await Promise.all([
    getTodos({ includeCancelled: true }),
    getMeetings({ page: 0, pageSize: 100 }),
  ]);

  return <TodoWorkspace initialTodos={todos.items} meetings={meetings.items} title="我的待办" />;
}
