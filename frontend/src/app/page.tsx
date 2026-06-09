/**
 * Server component that composes the home page. The Topbar sits
 * outside the main grid because it is sticky and the staggered
 * entry animation lives in <PageEntry>. The two main sections
 * (<SearchSection> and <ChatSection>) own their own state and
 * are imported from their respective sub-trees (T-007, T-008).
 *
 * The default Next.js page (the create-next-app template) is
 * intentionally removed — every line of UI in this file is part
 * of the v1 frontend contract.
 */
import { Topbar } from "@/components/layout/Topbar";
import { OnboardingOverlay } from "@/components/layout/OnboardingOverlay";
import { PageEntry, PageEntryItem } from "@/components/layout/PageEntry";
import { SearchSection } from "@/components/search/SearchSection";
import { ChatSection } from "@/components/chat/ChatSection";

export default function Home(): React.ReactElement {
  return (
    <>
      <Topbar />
      <PageEntry>
        <PageEntryItem className="mx-auto w-full max-w-7xl px-4 pt-6 md:px-6">
          <SearchSection />
        </PageEntryItem>
        <PageEntryItem className="mx-auto w-full max-w-7xl flex-1 px-4 pb-12 pt-6 md:px-6">
          <ChatSection />
        </PageEntryItem>
      </PageEntry>
      <OnboardingOverlay />
    </>
  );
}
