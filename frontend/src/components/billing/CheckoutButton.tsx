"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { CheckoutRequestBody } from "@/types/billing";

interface CheckoutButtonProps {
  priceInterval: CheckoutRequestBody["priceInterval"];
}

export function CheckoutButton({ priceInterval }: CheckoutButtonProps) {
  const t = useTranslations("Billing");
  const router = useRouter();
  // useRef double-click guard: while the request is in flight we
  // keep the button disabled AND a ref flag set so even programmatic
  // re-renders can't trigger a second POST.
  const inFlightRef = useRef(false);
  const [isPending, setIsPending] = useState(false);

  async function handleClick() {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setIsPending(true);
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priceInterval }),
      });
      if (!res.ok) {
        toast.error(t("errors.network"));
        return;
      }
      // The route 302-redirects to Stripe. In a normal browser this
      // never lands here, but if it does (e.g. fetch wrapper),
      // refresh the router so plan state repopulates after Stripe.
      const data = (await res.json().catch(() => null)) as { url?: string } | null;
      if (data?.url) {
        router.push(data.url);
      } else {
        router.refresh();
      }
    } catch {
      toast.error(t("errors.network"));
    } finally {
      inFlightRef.current = false;
      setIsPending(false);
    }
  }

  return (
    <Button onClick={handleClick} disabled={isPending} data-testid="checkout-button">
      {t("cta.upgrade")}
    </Button>
  );
}