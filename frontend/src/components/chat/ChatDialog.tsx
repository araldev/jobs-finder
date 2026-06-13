"use client";

import { useState } from "react";
import { X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ChatPanel } from "./ChatPanel";
import { Logo } from "@/components/layout/Logo";

export function ChatDialog() {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-shadow hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label="Open chat"
        >
          {open ? (
            <X className="h-6 w-6" />
          ) : (
            <Logo size="lg" className="rounded-full" />
          )}
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogTitle className="sr-only">Chat con IA</DialogTitle>
        <div className="h-[500px] overflow-hidden">
          <ChatPanel />
        </div>
      </DialogContent>
    </Dialog>
  );
}
