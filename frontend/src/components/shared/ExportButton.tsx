"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ExportButtonProps {
  onClick: () => void;
  loading?: boolean;
}

export function ExportButton({ onClick, loading }: ExportButtonProps) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={loading}>
      <Download className="mr-2 h-4 w-4" />
      {loading ? "Exporting..." : "Export CSV"}
    </Button>
  );
}
