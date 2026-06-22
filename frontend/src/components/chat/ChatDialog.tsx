"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bot, Sparkles, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ChatPanel } from "./ChatPanel";

export function ChatDialog() {
  const [open, setOpen] = useState(false);
  const t = useTranslations("Chat");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="group fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/80 text-primary-foreground shadow-lg transition-all hover:shadow-xl hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={t("fab.label")}
        >
          {open ? (
            <X className="h-6 w-6" />
          ) : (
            <span className="relative">
              <Bot className="h-6 w-6" />
              <Sparkles className="absolute -right-1.5 -top-1.5 h-3 w-3 text-yellow-300" />
            </span>
          )}
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogTitle className="sr-only">{t("dialog.title")}</DialogTitle>
        <div className="h-[500px] overflow-hidden">
          <ChatPanel />
        </div>
      </DialogContent>
    </Dialog>
  );
}