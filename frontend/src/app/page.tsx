/**
 * Server component that composes the home page. The Topbar sits
 * outside the main grid because it is sticky and the staggered
 * entry animation lives in <PageEntry>. The <Workbench> wrapper
 * is the single client-side seam — it owns the JobsOverride
 * context that lets the chat replace the results grid when its
 * `done` event arrives.
 */
import { Topbar } from "@/components/layout/Topbar";
import { OnboardingOverlay } from "@/components/layout/OnboardingOverlay";
import { PageEntry, PageEntryItem } from "@/components/layout/PageEntry";
import { Workbench } from "@/components/layout/Workbench";
import { SearchSection } from "@/components/search/SearchSection";
import { ChatSection } from "@/components/chat/ChatSection";

export default function Home(): React.ReactElement {
  return (
    <>
      <Topbar />
      <PageEntry>
        <PageEntryItem className="mx-auto w-full max-w-7xl px-4 pt-6 md:px-6">
          <Workbench>
            <div className="lg:flex-[2_2_0%]">
              <SearchSection />
            </div>
            <div className="lg:flex-1">
              <ChatSection />
            </div>
          </Workbench>
        </PageEntryItem>
      </PageEntry>
      <OnboardingOverlay />
    </>
  );
}
