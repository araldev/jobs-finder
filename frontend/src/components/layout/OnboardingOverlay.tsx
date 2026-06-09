"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sparkles, Search } from "lucide-react";

const STORAGE_KEY = "jobs-finder:onboarding-seen";

/**
 * First-time visitor onboarding. A single-screen modal that explains
 * the two main features and dismisses with a "Got it" button. State
 * persists in localStorage so it never shows again on the same device.
 * The Topbar exposes a Ctrl+Shift+R shortcut to reset the key for QA.
 */
export function OnboardingOverlay(): React.ReactElement | null {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const seen = window.localStorage.getItem(STORAGE_KEY);
    if (seen !== "true") setOpen(true);
  }, []);

  if (!mounted) return null;

  return (
    <AnimatePresence>
      {open ? (
        <Dialog
          open={open}
          onOpenChange={(next) => {
            if (!next) dismiss(setOpen);
          }}
        >
          <DialogContent
            showCloseButton={false}
            className="gap-6 border-border/60 sm:max-w-md"
          >
            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.99 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className="flex flex-col gap-6"
            >
              <DialogHeader>
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-accent/15 text-accent">
                    <Sparkles className="size-5" aria-hidden />
                  </span>
                  <DialogTitle className="text-lg">
                    Bienvenido a jobs-finder
                  </DialogTitle>
                </div>
                <DialogDescription className="space-y-3 pt-2 text-sm leading-relaxed text-muted-foreground">
                  <span className="block">
                    Busca puestos en LinkedIn, Indeed e InfoJobs en un solo
                    lugar. Escribe palabras clave y una ubicación para
                    empezar.
                  </span>
                  <span className="block">
                    Cuando tengas resultados, abre el chat a la derecha para
                    refinarlos en lenguaje natural:{" "}
                    <em>&ldquo;busco junior en Madrid&rdquo;</em>,{" "}
                    <em>&ldquo;remoto y en español&rdquo;</em>, o{" "}
                    <em>&ldquo;menos de 30 días&rdquo;</em>.
                  </span>
                </DialogDescription>
              </DialogHeader>
              <ul className="grid gap-2 text-sm">
                <li className="flex items-center gap-3 rounded-lg border border-border/60 bg-card/40 px-3 py-2">
                  <Search className="size-4 text-accent" aria-hidden />
                  <span>Búsqueda agregada en 3 fuentes</span>
                </li>
                <li className="flex items-center gap-3 rounded-lg border border-border/60 bg-card/40 px-3 py-2">
                  <Sparkles className="size-4 text-accent" aria-hidden />
                  <span>Refinamiento por chat con IA</span>
                </li>
              </ul>
              <DialogFooter>
                <Button
                  className="w-full"
                  onClick={() => dismiss(setOpen)}
                  autoFocus
                >
                  Entendido
                </Button>
              </DialogFooter>
            </motion.div>
          </DialogContent>
        </Dialog>
      ) : null}
    </AnimatePresence>
  );
}

function dismiss(setOpen: (open: boolean) => void): void {
  window.localStorage.setItem(STORAGE_KEY, "true");
  setOpen(false);
}
