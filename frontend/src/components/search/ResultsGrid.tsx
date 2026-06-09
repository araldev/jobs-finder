import { JobCard } from "./JobCard";
import type { Job } from "@/lib/types";

interface ResultsGridProps {
  readonly jobs: readonly Job[];
}

/**
 * Responsive grid for job cards. 1 column on mobile, 2 on tablet,
 * 3 on desktop. No glass — solid surfaces for legibility.
 */
export function ResultsGrid({ jobs }: ResultsGridProps): React.ReactElement {
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {jobs.map((job) => (
        <li key={job.id}>
          <JobCard job={job} />
        </li>
      ))}
    </ul>
  );
}
