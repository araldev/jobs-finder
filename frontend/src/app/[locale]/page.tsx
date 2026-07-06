"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { createClient } from "@/lib/supabase/client";
import founderPhoto from "@/assets/perfil_2_sin_fondo.webp";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Footer } from "@/components/layout/Footer";
import {
  Upload,
  FileText,
  Download,
  CheckCircle2,
  Sparkles,
  Zap,
  Shield,
  ArrowRight,
  Loader2,
  X,
  Menu,
} from "lucide-react";

interface SavedCV {
  id: string;
  original_filename: string;
  storage_path: string;
  created_at: string;
}

export default function CVLandingPage() {
  const supabase = createClient();
  const t = useTranslations("Landing");
  const [user, setUser] = useState<{ email?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [savedCV, setSavedCV] = useState<SavedCV | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Check auth state on mount
  const checkAuth = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    setUser(data.session?.user ?? null);

    if (data.session?.user) {
      // Fetch saved CV
      const { data: cvData } = await supabase
        .from("user_csv")
        .select("id, original_filename, storage_path, created_at")
        .eq("user_id", data.session.user.id)
        .maybeSingle();
      setSavedCV(cvData);
    }
    setLoading(false);
  }, [supabase]);

  // Re-check when page becomes visible (after login redirect)
  const handleFocus = useCallback(() => {
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.addEventListener("focus", handleFocus);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("focus", handleFocus);
      }
    };
  }, [handleFocus]);

  // Initial load
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      setError(t("upload.pdfOnly"));
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError(t("upload.tooBig"));
      return;
    }

    const { data: sessionData } = await supabase.auth.getSession();
    if (!sessionData.session?.user) {
      setError(t("upload.mustSignIn"));
      return;
    }

    setUploading(true);
    setError(null);

    const storagePath = `${sessionData.session.user.id}/cv.pdf`;
    const { error: storageError } = await supabase.storage
      .from("cvs")
      .upload(storagePath, file, { upsert: true });

    if (storageError) {
      setError(`Error subiendo archivo: ${storageError.message}`);
      setUploading(false);
      return;
    }

    const { error: dbError } = await supabase.from("user_csv").upsert({
      user_id: sessionData.session.user.id,
      original_filename: file.name,
      storage_path: storagePath,
    });

    if (dbError) {
      setError(`Error guardando referencia: ${dbError.message}`);
      setUploading(false);
      return;
    }

    setSavedCV({
      id: "",
      original_filename: file.name,
      storage_path: storagePath,
      created_at: new Date().toISOString(),
    });
    setUploadSuccess(true);
    setUploading(false);

    setTimeout(() => setUploadSuccess(false), 3000);
  }

  async function handleLogout() {
    await supabase.auth.signOut();
    setUser(null);
    setSavedCV(null);
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/favicon.svg" alt="Jobs Finder" width={36} height={36} className="h-9 w-9" />
            <span className="font-display text-xl font-bold">Jobs Finder</span>
          </Link>

          {/* Desktop nav */}
          <div className="hidden items-center gap-6 md:flex">
            <Link
              href="/search"
              prefetch={true}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Buscar empleos
            </Link>
            {!loading && (
              <>
                {user ? (
                  <div className="flex items-center gap-4">
                    <Link
                      href="/settings"
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {user.email}
                    </Link>
                    <Button variant="outline" size="sm" onClick={handleLogout}>
                      Cerrar sesión
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <Link href="/login">
                      <Button variant="ghost" size="sm">
                        Iniciar sesión
                      </Button>
                    </Link>
                    <Link href="/login">
                      <Button size="sm">Registrarse</Button>
                    </Link>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? (
              <X className="h-6 w-6" />
            ) : (
              <Menu className="h-6 w-6" />
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="border-t md:hidden">
            <div className="container mx-auto space-y-4 px-4 py-4">
              <Link
                href="/search"
                className="block text-sm text-muted-foreground"
                onClick={() => setMobileMenuOpen(false)}
              >
                Buscar empleos
              </Link>
              {!loading && !user && (
                <div className="flex flex-col gap-2">
                  <Link href="/login" onClick={() => setMobileMenuOpen(false)}>
                    <Button variant="outline" className="w-full">
                      Iniciar sesión
                    </Button>
                  </Link>
                  <Link href="/login" onClick={() => setMobileMenuOpen(false)}>
                    <Button className="w-full">Registrarse</Button>
                  </Link>
                </div>
              )}
              {user && (
                <div className="flex flex-col gap-2">
                  <Link
                    href="/settings"
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {user.email}
                  </Link>
                  <Button variant="outline" onClick={handleLogout}>
                    Cerrar sesión
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden py-20 md:py-32">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-secondary/5" />
        <div className="absolute top-20 right-0 h-[500px] w-[500px] rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute bottom-0 left-0 h-[400px] w-[400px] rounded-full bg-secondary/10 blur-3xl" />

        <div className="container relative mx-auto px-4">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border bg-muted/50 px-4 py-1.5 text-sm">
              <Sparkles className="h-4 w-4 text-primary" />
              <span className="text-muted-foreground">
                Potenciado por IA
              </span>
            </div>

            <h1 className="font-display text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl">
              {t.rich("hero.title", {
                highlight: (chunks) => (
                  <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
                    {chunks}
                  </span>
                ),
              })}
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground md:text-xl">
              {t("hero.subtitle")}
            </p>

            <div className="mt-10 flex flex-col items-center gap-4">
              {user ? (
                <div className="flex flex-col items-center gap-4">
                  <UploadCVSection
                    savedCV={savedCV}
                    uploading={uploading}
                    uploadSuccess={uploadSuccess}
                    error={error}
                    onUpload={handleUpload}
                  />
                  <p className="text-sm text-muted-foreground">
                    Una vez guardado, úsalo desde{" "}
                    <Link href="/search" className="text-primary hover:underline">
                      cualquier oferta de empleo
                    </Link>{" "}
                    para generar tu CV adaptado
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3 w-full max-w-md">
                  <label className="cursor-not-allowed">
                    <input
                      type="file"
                      accept="application/pdf"
                      className="hidden"
                      disabled
                    />
                    <div className="rounded-xl border-2 border-dashed border-border p-8 text-center opacity-60">
                      <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
                      <p className="font-medium text-sm mt-3">
                        {t("hero.guestUploadTitle")}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {t("hero.guestUploadHint")}
                      </p>
                    </div>
                  </label>
                  <Link href="/login">
                    <Button size="lg" className="w-full gap-2">
                      {t("hero.guestCta")}
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Link>
                </div>
              )}
            </div>

            {/* Stats removed — see landing refactor 2026-07 for rationale (no real users yet) */}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-muted/30 py-20">
        <div className="container mx-auto px-4">
          <div className="mb-12 text-center">
            <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
              ¿Cómo funciona?
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
              Tres pasos simples para adaptar tu CV a cualquier oferta de
              empleo
            </p>
          </div>

          <div className="mx-auto grid max-w-4xl gap-8 md:grid-cols-3">
            <Card className="relative overflow-hidden">
              <CardContent className="pt-6">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
                  <Upload className="h-6 w-6 text-primary" />
                </div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-primary">
                    01
                  </span>
                  <h3 className="font-display text-lg font-bold">
                    Sube tu CV
                  </h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  Sube tu CV en PDF una sola vez. Lo guardamos de forma
                  segura para que lo uses cuando quieras.
                </p>
              </CardContent>
            </Card>

            <Card className="relative overflow-hidden">
              <CardContent className="pt-6">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-secondary/10">
                  <FileText className="h-6 w-6 text-secondary" />
                </div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-secondary">
                    02
                  </span>
                  <h3 className="font-display text-lg font-bold">
                    Selecciona una oferta
                  </h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  Elige el empleo que te interesa. Nuestra IA analiza la
                  oferta y adapta tu CV automáticamente.
                </p>
              </CardContent>
            </Card>

            <Card className="relative overflow-hidden">
              <CardContent className="pt-6">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10">
                  <Download className="h-6 w-6 text-accent" />
                </div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-accent">
                    03
                  </span>
                  <h3 className="font-display text-lg font-bold">
                    Descarga y aplica
                  </h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  Descarga tu CV adaptado en PDF listo para enviar.
                  Optimizado para pasar filtros ATS.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Benefits */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
            <div>
              <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
                ¿Por qué funciona?
              </h2>
              <p className="mt-4 text-lg text-muted-foreground">
                La mayoría de los CVs son descartados en los primeros 7
                segundos. Nuestro sistema asegura que el tuyo pase el
                filtro.
              </p>

              <div className="mt-8 space-y-4">
                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                    <Zap className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-display font-bold">
                      Adaptación instantánea
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Nuestra IA identifica las keywords y habilidades
                      clave de cada oferta y las destaca en tu CV.
                    </p>
                  </div>
                </div>

                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary/10">
                    <Shield className="h-5 w-5 text-secondary" />
                  </div>
                  <div>
                    <h3 className="font-display font-bold">
                      Optimizado para ATS
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Los sistemas de tracking de candidatos (ATS)
                      premian CVs que coinciden con la descripción del
                      empleo.
                    </p>
                  </div>
                </div>

                <div className="flex gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10">
                    <Sparkles className="h-5 w-5 text-accent" />
                  </div>
                  <div>
                    <h3 className="font-display font-bold">
                      Sin esfuerzo, máximo impacto
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Genera tantos CVs adaptados como ofertas te
                      interesen. En minutos, tienes un CV a medida.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-secondary/10 blur-3xl" />
              <Card className="relative overflow-hidden">
                <div className="aspect-video bg-muted/30 flex items-center justify-center">
                  <p className="text-sm text-muted-foreground">
                    Demo del flujo: CV → oferta → CV adaptado (próximamente)
                  </p>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials section removed — see landing refactor 2026-07 (no real users yet, no real quotes) */}

      {/* Founder story */}
      <section className="py-16">
        <div className="container mx-auto px-4 max-w-3xl">
          <Card>
            <CardContent className="p-8">
              <div className="flex flex-col md:flex-row gap-6 items-start">
                <Image
                  src={founderPhoto}
                  alt="Arturo — fundador de Jobs Finder"
                  width={80}
                  height={80}
                  className="h-20 w-20 rounded-full object-cover shrink-0"
                />
                <div>
                  <p className="text-sm uppercase tracking-wide text-muted-foreground mb-2">
                    {t("founder.kicker")}
                  </p>
                  <h3 className="font-display text-xl font-bold mb-3">
                    {t("founder.title")}
                  </h3>
                  <p className="text-muted-foreground leading-relaxed">
                    {t("founder.body")}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FAQ */}
      <section className="bg-muted/30 py-16">
        <div className="container mx-auto px-4 max-w-2xl">
          <h2 className="font-display text-2xl font-bold mb-8 text-center">
            {t("faq.title")}
          </h2>
          <div className="space-y-4">
            <details className="rounded-lg border bg-card p-4">
              <summary className="font-medium cursor-pointer">
                {t("faq.q1.question")}
              </summary>
              <p className="mt-3 text-sm text-muted-foreground">
                {t("faq.q1.answer")}
              </p>
            </details>
            <details className="rounded-lg border bg-card p-4">
              <summary className="font-medium cursor-pointer">
                {t("faq.q2.question")}
              </summary>
              <p className="mt-3 text-sm text-muted-foreground">
                {t("faq.q2.answer")}
              </p>
            </details>
            <details className="rounded-lg border bg-card p-4">
              <summary className="font-medium cursor-pointer">
                {t("faq.q3.question")}
              </summary>
              <p className="mt-3 text-sm text-muted-foreground">
                {t("faq.q3.answer")}
              </p>
            </details>
            <details className="rounded-lg border bg-card p-4">
              <summary className="font-medium cursor-pointer">
                {t("faq.q4.question")}
              </summary>
              <p className="mt-3 text-sm text-muted-foreground">
                {t("faq.q4.answer")}
              </p>
            </details>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
              Empieza ahora
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-muted-foreground">
              Sube tu CV y genera tu primera versión adaptada en menos
              de 3 minutos. Es gratis.
            </p>

            <div className="mt-8 flex flex-col items-center gap-4">
              {user ? (
                <UploadCVSection
                  savedCV={savedCV}
                  uploading={uploading}
                  uploadSuccess={uploadSuccess}
                  error={error}
                  onUpload={handleUpload}
                />
              ) : (
                <Link href="/login">
                  <Button size="lg" className="gap-2 text-base">
                    Registrarse gratis
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              )}
             </div>
           </div>
         </div>
       </section>

      <Footer />
    </div>
  );
}

// Upload CV Section (inline, reuses auth state from parent)
function UploadCVSection({
  savedCV,
  uploading,
  uploadSuccess,
  error,
  onUpload,
}: {
  savedCV: SavedCV | null;
  uploading: boolean;
  uploadSuccess: boolean;
  error: string | null;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="w-full max-w-md">
      <label className="cursor-pointer">
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={onUpload}
          disabled={uploading}
        />
        {savedCV ? (
          <div className="flex items-center justify-center gap-3 rounded-xl border bg-card p-4 transition-colors hover:bg-muted/50">
            <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
            <div className="text-left">
              <p className="font-medium text-sm">{savedCV.original_filename}</p>
              <p className="text-xs text-muted-foreground">
                Tu CV está guardado
              </p>
            </div>
            <span className="ml-auto text-xs text-primary">
              Actualizar
            </span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border p-8 transition-colors hover:border-primary/50">
            {uploading ? (
              <>
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">
                  Subiendo tu CV...
                </p>
              </>
            ) : uploadSuccess ? (
              <>
                <CheckCircle2 className="h-8 w-8 text-green-600" />
                <p className="text-sm text-green-600">¡CV subido!</p>
              </>
            ) : (
              <>
                <Upload className="h-8 w-8 text-muted-foreground" />
                <div className="text-center">
                  <p className="font-medium text-sm">
                    Sube tu CV (PDF)
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Arrastra o haz click para seleccionar
                  </p>
                </div>
              </>
            )}
          </div>
        )}
      </label>
      {error && (
        <p className="mt-2 text-center text-sm text-destructive">{error}</p>
      )}
    </div>
  );
}
