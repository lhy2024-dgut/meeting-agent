export const dynamic = "force-dynamic";

import { ContactsWorkspace } from "@/components/contacts/contacts-workspace";
import { getContactGroups, getContacts } from "@/lib/api";

export default async function ContactsPage() {
  let initialData: { contacts: Awaited<ReturnType<typeof getContacts>>; groups: Awaited<ReturnType<typeof getContactGroups>> } | null = null;
  try {
    const [contacts, groups] = await Promise.all([getContacts(), getContactGroups()]);
    initialData = { contacts, groups };
  } catch {
    initialData = null;
  }

  if (!initialData) {
    return <ContactsWorkspace />;
  }

  return (
    <ContactsWorkspace
      initialContacts={initialData.contacts.items}
      initialGroups={initialData.groups.items}
    />
  );
}
