"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { createClient } from "@/lib/supabase/client";
import { PageTransition } from "@/components/layout/PageTransition";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Upload, FileText, Download, Loader2, CheckCircle2, X } from "lucide-react";

interface SavedCV {
  id: string;
  original_filename: string;
  storage_path: string;
}

interface PersistedState {
  status: "idle" | "uploading" | "done" | "error";
  downloadUrl: string | null;
  errorMsg: string | null;
}

const STORAGE_KEY = "cv-custom-gen";

function readPersistedState(): PersistedState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistedState) : null;
  } catch {
    return null;
  }
}

function writePersistedState(state: PersistedState) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage full or unavailable — silently ignore
  }
}

function clearPersistedState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export default function AdaptCVPage() {
  const t = useTranslations("AdaptCV");

  const [savedCV, setSavedCV] = useState<SavedCV | null>(null);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [jobUrl, setJobUrl] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobCompany, setJobCompany] = useState("");

  // Restore generation state from sessionStorage
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">(
    () => readPersistedState()?.status ?? "idle",
  );
  const [downloadUrl, setDownloadUrl] = useState<string | null>(
    () => readPersistedState()?.downloadUrl ?? null,
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(
    () => readPersistedState()?.errorMsg ?? null,
  );

  const [loadingSavedCV, setLoadingSavedCV] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const supabase = createClient();

  // Persist generation state to sessionStorage
  useEffect(() => {
    writePersistedState({ status, downloadUrl, errorMsg });
  }, [status, downloadUrl, errorMsg]);

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

  useEffect(() => {
    fetchSavedCV();
  }, [fetchSavedCV]);

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

  function removeFile() {
    setCvFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const hasUrlOrDescription = jobUrl.trim().length > 0 || jobDescription.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Need either a selected file or a saved CV
    if (!cvFile && !savedCV) {
      setErrorMsg(t("errors.noCV"));
      return;
    }

    // Need at least URL or description
    if (!hasUrlOrDescription) {
      setErrorMsg(t("errors.noInput"));
      return;
    }

    setStatus("uploading");
    setErrorMsg(null);

    let fileToSend: File;

    if (cvFile) {
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

      fileToSend = new File([storageData], savedCV!.original_filename, {
        type: "application/pdf",
      });
    }

    const formData = new FormData();
    formData.append("file", fileToSend);
    if (jobUrl.trim()) formData.append("job_url", jobUrl.trim());
    if (jobDescription.trim()) formData.append("job_description", jobDescription.trim());
    if (jobTitle.trim()) formData.append("job_title", jobTitle.trim());
    if (jobCompany.trim()) formData.append("job_company", jobCompany.trim());

    try {
      const res = await fetch("/api/cv/generate-custom", {
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
      setErrorMsg(err instanceof Error ? err.message : t("errors.generic"));
      setStatus("error");
    }
  }

  function handleReset() {
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    clearPersistedState();
    setCvFile(null);
    setJobUrl("");
    setJobDescription("");
    setJobTitle("");
    setJobCompany("");
    setStatus("idle");
    setDownloadUrl(null);
    setErrorMsg(null);
    setConsentGiven(false);
  }

  return (
    <PageTransition>
      <div className="mx-auto max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle>{t("title")}</CardTitle>
            <CardDescription>{t("subtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            {status === "done" && downloadUrl ? (
              <div className="flex flex-col items-center gap-4 py-6">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                  <FileText className="h-7 w-7 text-primary" />
                </div>
                <p className="text-center text-sm text-muted-foreground">
                  {t("successMessage")}
                </p>
                <Button asChild>
                  <a
                    href={downloadUrl}
                    download="CV-adaptado.pdf"
                    className="inline-flex items-center gap-2"
                  >
                    <Download className="h-4 w-4" />
                    {t("download")}
                  </a>
                </Button>
                <button
                  onClick={handleReset}
                  className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
                  type="button"
                >
                  {t("generateAnother")}
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Saved CV indicator */}
                {!loadingSavedCV && savedCV && !cvFile && (
                  <div
                    className="flex cursor-pointer items-center gap-3 rounded-lg border bg-muted/50 p-3 transition-colors hover:bg-muted"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {savedCV.original_filename}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {t("changeCv")}
                      </p>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {t("savedCvLabel")}
                    </span>
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
                          removeFile();
                        }}
                        className="inline-flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
                      >
                        <X className="h-3 w-3" />
                        Quitar
                      </button>
                    </>
                  ) : (
                    <>
                      <Upload className="h-8 w-8 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">
                        {savedCV
                          ? "O arrastrá un PDF diferente para esta adaptación"
                          : "Arrastrá tu CV PDF o click para seleccionar"}
                      </p>
                    </>
                  )}
                </div>

                {/* URL input */}
                <div className="space-y-2">
                  <label htmlFor="job-url" className="text-sm font-medium">
                    {t("url")}
                  </label>
                  <Input
                    id="job-url"
                    type="url"
                    placeholder={t("urlPlaceholder")}
                    value={jobUrl}
                    onChange={(e) => setJobUrl(e.target.value)}
                  />
                </div>

                {/* Description textarea */}
                <div className="space-y-2">
                  <label htmlFor="job-description" className="text-sm font-medium">
                    {t("description")}
                  </label>
                  <textarea
                    id="job-description"
                    rows={5}
                    placeholder={t("descriptionPlaceholder")}
                    value={jobDescription}
                    onChange={(e) => setJobDescription(e.target.value)}
                    className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  {jobDescription.length > 0 && (
                    <p className="text-right text-xs text-muted-foreground">
                      {jobDescription.length} caracteres
                    </p>
                  )}
                </div>

                {/* URL or description hint */}
                {!hasUrlOrDescription && (
                  <p className="text-xs text-muted-foreground">
                    {t("urlOrDescription")}
                  </p>
                )}

                {/* Optional fields row */}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <label htmlFor="job-title" className="text-sm font-medium">
                      {t("titleLabel")}
                    </label>
                    <Input
                      id="job-title"
                      type="text"
                      value={jobTitle}
                      onChange={(e) => setJobTitle(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="job-company" className="text-sm font-medium">
                      {t("company")}
                    </label>
                    <Input
                      id="job-company"
                      type="text"
                      value={jobCompany}
                      onChange={(e) => setJobCompany(e.target.value)}
                    />
                  </div>
                </div>

                {/* Consent for LLM processing */}
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <label className="flex cursor-pointer items-start gap-3">
                    <input
                      type="checkbox"
                      checked={consentGiven}
                      onChange={(e) => setConsentGiven(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border text-primary accent-primary"
                      required
                    />
                    <span className="text-xs text-muted-foreground">
                      {t.rich("consent", {
                        strong: (chunks) => (
                          <strong className="text-foreground">{chunks}</strong>
                        ),
                        privacy: (chunks) => (
                          <Link
                            href="/privacidad"
                            target="_blank"
                            className="underline underline-offset-2 hover:text-foreground"
                          >
                            {chunks}
                          </Link>
                        ),
                      })}
                    </span>
                  </label>
                </div>

                {/* Error message */}
                {errorMsg && (
                  <p className="text-sm text-destructive">{errorMsg}</p>
                )}

                {/* Submit button */}
                <Button
                  type="submit"
                  disabled={(!cvFile && !savedCV) || !hasUrlOrDescription || !consentGiven}
                  className="w-full"
                >
                  {status === "uploading" ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t("downloading")}
                    </span>
                  ) : (
                    t("submit")
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </PageTransition>
  );
}
