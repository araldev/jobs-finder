interface SalaryBadgeProps {
  salary: string | null;
}

export function SalaryBadge({ salary }: SalaryBadgeProps) {
  if (!salary) return null;
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      {salary}
    </span>
  );
}
