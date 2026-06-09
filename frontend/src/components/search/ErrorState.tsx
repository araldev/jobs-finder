"use client";

import { CircleAlert, RotateCcw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

interface ErrorStateProps {
  readonly error: unknown;
  readonly onRetry: () => void;
}

function extractApiError(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null;
}

export function ErrorState({ error, onRetry }: ErrorStateProps): React.ReactElement {
  const apiError = extractApiError(error);
  return (
    <Alert variant="destructive" className="rounded-2xl">
      <CircleAlert aria-hidden className="size-4" />
      <AlertTitle>No pudimos cargar los resultados</AlertTitle>
      <AlertDescription>
        <p>
          {apiError?.message ?? "Error inesperado, intenta de nuevo."}{" "}
          {apiError?.requestId ? (
            <span className="block text-xs opacity-80">
              Referencia: <code className="font-mono">{apiError.requestId}</code>
            </span>
          ) : null}
        </p>
        <Button
          size="sm"
          variant="outline"
          className="mt-3"
          onClick={onRetry}
        >
          <RotateCcw aria-hidden className="size-3.5" />
          Reintentar
        </Button>
      </AlertDescription>
    </Alert>
  );
}
