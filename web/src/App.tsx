import { AppShell } from "./components/AppShell";
import { TodayPage } from "./pages/TodayPage";
import { AllEventsPage } from "./pages/AllEventsPage";
import { EventDetailPage } from "./pages/EventDetailPage";
import { WatchlistPage } from "./pages/WatchlistPage";

export default function App() {
  const path = window.location.pathname;
  const eventMatch = path.match(/^\/events\/(evt_[a-zA-Z0-9_-]+)$/);
  const page = eventMatch
    ? <EventDetailPage eventId={eventMatch[1]!} />
    : path === "/watchlist"
      ? <WatchlistPage />
    : path === "/events"
      ? <AllEventsPage />
      : <TodayPage />;
  return (
    <AppShell>
      {page}
    </AppShell>
  );
}
