"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import type { Job } from "@/types/job";
import { Upload, FileText, Download, X, Loader2, CheckCircle2 } from "lucide-react";
import { useCVAdapted } from "@/hooks/useCVAdapted";

interface GenerateCVModalProps {
  job: Job;
  trigger: React.ReactNode;
}

interface SavedCV {
  id: string;
  original_filename: string;
  storage_path: string;
}

export function GenerateCVModal({ job, trigger }: GenerateCVModalProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [savedCV, setSavedCV] = useState<SavedCV | null>(null);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [loadingSavedCV, setLoadingSavedCV] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const supabase = createClient();
  const { incrementCVAdapted } = useCVAdapted();

  // Track CV adaptation count when successfully generated
  useEffect(() => {
    if (status === "done") {
      incrementCVAdapted();
    }
  }, [status, incrementCVAdapted]);

  const fetchSavedCV = useCallback(async () => {
    setLoadingSavedCV(true);
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      setLoadingSavedCV(false);
      return;
    }

    const { data } = await supabase
      .from("user_csv")
      .select("id, original_filename, storage_path")
      .eq("user_id", user.id)
      .maybeSingle();

    setSavedCV(data);
    setLoadingSavedCV(false);
  }, [supabase]);

  function open() {
    setIsOpen(true);
    setCvFile(null);
    setStatus("idle");
    setErrorMsg(null);
    setDownloadUrl(null);
    setConsentGiven(false);
    fetchSavedCV();
  }

  function close() {
    setIsOpen(false);
    if (downloadUrl) {
      URL.revokeObjectURL(downloadUrl);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) {
      if (f.type !== "application/pdf") {
        setErrorMsg("Solo se aceptan archivos PDF");
        return;
      }
      setCvFile(f);
      setErrorMsg(null);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) {
      if (f.type !== "application/pdf") {
        setErrorMsg("Solo se aceptan archivos PDF");
        return;
      }
      setCvFile(f);
      setErrorMsg(null);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Need either a selected file or a saved CV
    if (!cvFile && !savedCV) {
      setErrorMsg("Subí tu CV o guardalo primero en Settings");
      return;
    }

    setStatus("uploading");
    setErrorMsg(null);

    let fileToSend: File;

    if (cvFile) {
      // User selected a file manually
      fileToSend = cvFile;
    } else {
      // Download saved CV from Supabase Storage
      const { data: storageData, error: storageError } = await supabase.storage
        .from("cvs")
        .download(savedCV!.storage_path);

      if (storageError || !storageData) {
        setErrorMsg("No pude descargar tu CV guardado");
        setStatus("error");
        return;
      }

      // Create a File object from the blob
      fileToSend = new File([storageData], savedCV!.original_filename, {
        type: "application/pdf",
      });
    }

    const formData = new FormData();
    formData.append("file", fileToSend);
    formData.append("job_title", job.title);
    formData.append("job_company", job.company);
    formData.append("job_description", job.description ?? "");
    formData.append("job_url", job.url);

    try {
      const res = await fetch("/api/cv/generate", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(data.error ?? `HTTP ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setDownloadUrl(url);
      setStatus("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Error generando el CV");
      setStatus("error");
    }
  }

  return (
    <>
      <span onClick={open} className="cursor-pointer">
        {trigger}
      </span>

      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          <div className="relative w-full max-w-md rounded-xl border bg-card p-6 shadow-lg">
            <button
              onClick={close}
              className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
              type="button"
            >
              <X className="h-4 w-4" />
            </button>

            <h2 className="mb-1 font-display text-lg font-bold">
              Generar CV adaptado
            </h2>
            <p className="mb-4 text-sm text-muted-foreground">
              Adaptando CV para{" "}
              <strong>{job.company}</strong> — {job.title}
            </p>

            {status === "done" && downloadUrl ? (
              <div className="flex flex-col items-center gap-4 py-6">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                  <FileText className="h-7 w-7 text-primary" />
                </div>
                <p className="text-center text-sm text-muted-foreground">
                  Tu CV está listo. Descárgalo y úsalo para aplicar.
                </p>
                <a
                  href={downloadUrl}
                  download="CV-adaptado.pdf"
                  className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
                >
                  <Download className="h-4 w-4" />
                  Descargar CV (PDF)
                </a>
                <button
                  onClick={() => {
                    setCvFile(null);
                    setStatus("idle");
                    setDownloadUrl(null);
                    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
                  }}
                  className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
                  type="button"
                >
                  Generar otro
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Saved CV indicator */}
                {!loadingSavedCV && savedCV && !cvFile && (
                  <div
                    className="flex cursor-pointer items-center gap-3 rounded-lg border bg-muted/50 p-3 transition-colors hover:bg-muted"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium">
                        {savedCV.original_filename}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Tu CV guardado — click para cambiar
                      </p>
                    </div>
                  </div>
                )}

                {/* File drop zone */}
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => fileInputRef.current?.click()}
                  className="flex cursor-pointer flex-col items-center gap-3 rounded-lg border-2 border-dashed border-border p-6 transition-colors hover:border-primary/50"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {cvFile ? (
                    <>
                      <FileText className="h-8 w-8 text-primary" />
                      <p className="text-sm font-medium">{cvFile.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(cvFile.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setCvFile(null);
                        }}
                        className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
                      >
                        Quitar
                      </button>
                    </>
                  ) : (
                    <>
                      <Upload className="h-8 w-8 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">
                        {savedCV
                          ? "O arrastrá un PDF diferente para esta postulación"
                          : "Arrastrá tu CV PDF o click para seleccionar"}
                      </p>
                    </>
                  )}
                </div>

                {errorMsg && (
                  <p className="text-sm text-destructive">{errorMsg}</p>
                )}

                {/* Consent for LLM processing (international transfer to USA) */}
                <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={consentGiven}
                      onChange={(e) => setConsentGiven(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border text-primary accent-primary"
                      required
                    />
                    <span className="text-xs text-muted-foreground">
                      Entiendo y acepto que mi CV sea procesado por{" "}
                      <strong className="text-foreground">nuestro proveedor de IA</strong>{" "}
                      para generar el CV adaptado.{" "}
                      <Link
                        href="/privacidad"
                        target="_blank"
                        className="underline underline-offset-2 hover:text-foreground"
                      >
                        Ver Política de Privacidad
                      </Link>
                    </span>
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={(!cvFile && !savedCV) || !consentGiven}
                  className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {status === "uploading" ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Generando CV...
                    </span>
                  ) : (
                    "Generar CV adaptado"
                  )}
                </button>

                {savedCV && (
                  <p className="text-center text-xs text-muted-foreground">
                    Se usará tu CV guardado. Subí un PDF para usar ese
                    temporalmente.
                  </p>
                )}

                <p className="text-center text-xs text-muted-foreground">
                  Tu CV será procesado por nuestro proveedor de IA.{" "}
                  <Link
                    href="/privacidad"
                    target="_blank"
                    className="underline underline-offset-2 hover:text-foreground"
                  >
                    Más información
                  </Link>
                </p>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
