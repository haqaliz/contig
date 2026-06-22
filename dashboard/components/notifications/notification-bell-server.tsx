// Server wrapper for the header bell. It does the disk read (getNotifications,
// which is server-only) and hands the events to the client island. Kept separate
// so the layout stays declarative and the data fetch never leaks into a client
// component. Rendered in the header, so it runs on every page.
import { getNotifications } from "@/lib/runs";
import { NotificationBell } from "@/components/notifications/notification-bell";

export async function NotificationBellServer() {
  const events = await getNotifications();
  return <NotificationBell events={events} />;
}
