import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { renderWithIntl } from "@/test-utils";
import RootLoading from "../loading";

describe("[locale]/loading (root loading)", () => {
  it("renders the latency hint <p> below the card skeletons", () => {
    // The root loading boundary is an RSC; in the test environment
    // it renders as a plain function component (no Next.js request
    // runtime is needed — the hint is a static <p> after the
    // skeleton grid). We wrap with renderWithIntl so the
    // LoadingHint child can resolve `useTranslations("Common")`.
    const { container } = render(renderWithIntl(<RootLoading />));

    // 5 job-card skeletons (the root loading shows the recent-jobs
    // area: stats row + 5 card skeletons). Use the rounded-xl
    // h-[140px] marker that is unique to the job-card skeletons.
    const jobCardSkeletons = container.querySelectorAll(
      "div.h-\\[140px\\].rounded-xl",
    );
    expect(jobCardSkeletons.length).toBe(5);

    // The latency hint is the only <p> in the root loading.
    // It uses the `Common.loadingHint` translation key.
    const hint = container.querySelector("p.mt-3.text-center.text-xs");
    expect(hint).not.toBeNull();
    // The hint text is the resolved translation (EN or ES), never
    // the raw i18n key. Both locales end in "… primera vez." (ES)
    // or "… on first load." (EN).
    const hintText = hint?.textContent ?? "";
    expect(hintText.length).toBeGreaterThan(0);
    expect(hintText).not.toBe("Common.loadingHint");
  });
});
