import type { Metadata } from "next";
import "../../globals.css";

export const metadata: Metadata = {
  title: "jobs.finder - Tu CV destaca en cada oferta",
  description:
    "Genera un CV adaptado a cada oferta de empleo usando inteligencia artificial. Sube tu CV, selecciona una oferta y descarga tu versión personalizada.",
};

export default function CVLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
