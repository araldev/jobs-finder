"use client";

import { type ReactNode } from "react";
import { JobsOverrideProvider } from "./JobsOverrideContext";

interface WorkbenchProps {
  readonly children: ReactNode;
}

/**
 * Client-side workbench that wraps the search and chat sections
 * in a single provider tree. Owns the JobsOverride context that
 * lets the chat's `done` event replace the results grid with the
 * filtered subset returned by the LLM.
 */
export function Workbench({ children }: WorkbenchProps): React.ReactElement {
  return (
    <JobsOverrideProvider>
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-2 md:px-6 lg:flex-row">
        {children}
      </div>
    </JobsOverrideProvider>
  );
}
