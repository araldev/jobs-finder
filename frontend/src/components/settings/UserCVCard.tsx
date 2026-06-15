"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { FileText, Upload, Trash2, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SavedCV {
  id: string;
  original_filename: string;
  storage_path: string;
  created_at: string;
}

export function UserCVCard() {
  const supabase = createClient();
  const [savedCV, setSavedCV] = useState<SavedCV | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const fetchCV = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    const { data, error: fetchError } = await supabase
      .from("user_csv")
      .select("id, original_filename, storage_path, created_at")
      .eq("user_id", user.id)
      .maybeSingle();

    if (fetchError) {
      setError("Error cargando tu CV");
    } else {
      setSavedCV(data);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    fetchCV();
  }, [fetchCV]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      setError("Solo se aceptan archivos PDF");
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError("El archivo debe ser menor a 5MB");
      return;
    }

    setUploading(true);
    setError(null);
    setMessage(null);

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      setError("No estás autenticado");
      setUploading(false);
      return;
    }

    // Upload to Supabase Storage
    const storagePath = `${user.id}/cv.pdf`;
    const { error: storageError } = await supabase.storage
      .from("cvs")
      .upload(storagePath, file, { upsert: true });

    if (storageError) {
      setError(`Error subiendo archivo: ${storageError.message}`);
      setUploading(false);
      return;
    }

    // Save record in user_csv table
    const { error: dbError } = await supabase.from("user_csv").upsert({
      user_id: user.id,
      original_filename: file.name,
      storage_path: storagePath,
    }, { onConflict: "user_id" });

    if (dbError) {
      setError(`Error guardando referencia: ${dbError.message}`);
      setUploading(false);
      return;
    }

    setMessage("CV guardado correctamente");
    setUploading(false);
    await fetchCV();
  }

  async function handleDelete() {
    if (!savedCV) return;

    setDeleting(true);
    setError(null);
    setMessage(null);

    // Delete from storage
    const { error: storageError } = await supabase.storage
      .from("cvs")
      .remove([savedCV.storage_path]);

    if (storageError) {
      setError(`Error eliminando archivo: ${storageError.message}`);
      setDeleting(false);
      return;
    }

    // Delete from database
    const { error: dbError } = await supabase
      .from("user_csv")
      .delete()
      .eq("id", savedCV.id);

    if (dbError) {
      setError(`Error eliminando referencia: ${dbError.message}`);
      setDeleting(false);
      return;
    }

    setSavedCV(null);
    setMessage("CV eliminado");
    setDeleting(false);
  }

  if (loading) {
    return (
      <div className="rounded-xl border bg-card p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Cargando...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <FileText className="h-4 w-4 text-primary" />
        <h3 className="font-medium text-sm">Tu CV</h3>
      </div>

      {savedCV ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-lg bg-muted p-3">
            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{savedCV.original_filename}</p>
              <p className="text-xs text-muted-foreground">
                Guardado el {new Date(savedCV.created_at).toLocaleDateString("es-ES")}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <label className="flex-1">
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={handleUpload}
                disabled={uploading}
              />
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                disabled={uploading}
                type="button"
                onClick={() => {
                  const input = document.querySelector(
                    "input[type=file]",
                  ) as HTMLInputElement;
                  input?.click();
                }}
              >
                {uploading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="mr-2 h-4 w-4" />
                )}
                {uploading ? "Subiendo..." : "Actualizar CV"}
              </Button>
            </label>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDelete}
              disabled={deleting}
              className="text-muted-foreground hover:text-destructive"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Subí tu CV para usarlo directamente al generar CVs adaptados.
          </p>
          <label>
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
            <Button
              variant="default"
              size="sm"
              className="w-full"
              disabled={uploading}
              type="button"
              onClick={() => {
                const input = document.querySelector(
                  "input[type=file]",
                ) as HTMLInputElement;
                input?.click();
              }}
            >
              {uploading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              {uploading ? "Subiendo..." : "Subir CV (PDF)"}
            </Button>
          </label>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      {message && <p className="mt-2 text-xs text-green-600">{message}</p>}
    </div>
  );
}
