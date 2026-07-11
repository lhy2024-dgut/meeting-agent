export const dynamic = "force-dynamic";

import { ContactsWorkspace } from "@/components/contacts/contacts-workspace";
import { getContactGroups, getContacts } from "@/lib/api";

export default async function ContactsPage() {
  try {
    const [contacts, groups] = await Promise.all([getContacts(), getContactGroups()]);
    return (
      <ContactsWorkspace
        initialContacts={contacts.items}
        initialGroups={groups.items}
      />
    );
  } catch {
    return <ContactsWorkspace />;
  }
}
