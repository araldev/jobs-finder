import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { Card, CardContent } from "@/components/ui/card";
import { Footer } from "@/components/layout/Footer";

export const metadata: Metadata = {
  title: "Política de Privacidad — Jobs Finder",
  description:
    "Política de privacidad de Jobs Finder. Cómo recopilamos, usamos y protegemos tus datos personales, incluyendo la transferencia internacional a Groq (EE.UU.).",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center px-4">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/favicon.svg" alt="Jobs Finder" width={36} height={36} className="h-9 w-9" />
            <span className="font-display text-xl font-bold">Jobs Finder</span>
          </Link>
        </div>
      </nav>

      <main className="container mx-auto max-w-3xl px-4 py-12">
        <h1 className="font-display text-4xl font-bold tracking-tight mb-2">
          Política de Privacidad
        </h1>
        <p className="text-sm text-muted-foreground mb-8">
          Última actualización: 15 de junio de 2026
        </p>

        <div className="space-y-8">
          {/* Índice */}
          <Card>
            <CardContent className="p-6">
              <h2 className="font-display text-lg font-bold mb-3">
                Índice
              </h2>
              <ol className="space-y-1 text-sm text-muted-foreground list-decimal list-inside">
                <li><a href="#responsable" className="hover:text-foreground">Responsable del tratamiento</a></li>
                <li><a href="#datos" className="hover:text-foreground">Datos que recopilamos</a></li>
                <li><a href="#finalidad" className="hover:text-foreground">Finalidad del tratamiento</a></li>
                <li><a href="#base-legal" className="hover:text-foreground">Base legal</a></li>
                <li><a href="#transferencia" className="hover:text-foreground">Transferencia internacional (EE.UU.)</a></li>
                <li><a href="#retencion" className="hover:text-foreground">Retención de datos</a></li>
                <li><a href="#tus-derechos" className="hover:text-foreground">Tus derechos</a></li>
                <li><a href="#seguridad" className="hover:text-foreground">Seguridad</a></li>
                <li><a href="#actualizaciones" className="hover:text-foreground">Actualizaciones</a></li>
                <li><a href="#contacto" className="hover:text-foreground">Contacto</a></li>
              </ol>
            </CardContent>
          </Card>

          {/* 1. Responsable */}
          <section id="responsable">
            <h2 className="font-display text-2xl font-bold mb-3">
              1. Responsable del tratamiento
            </h2>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                <strong className="text-foreground">Jobs Finder</strong> (en adelante,
                &ldquo;nosotros&rdquo;, &ldquo;la plataforma&rdquo; o &ldquo;Jobs Finder&rdquo;)
                es responsable del tratamiento de tus datos personales en el marco de
                esta política de privacidad.
              </p>
              <p>
                <strong className="text-foreground">Contacto:</strong>{" "}
                <a href="mailto:privacidad@jobsfinder.example.com" className="text-primary hover:underline">
                  privacidad@jobsfinder.example.com
                </a>
              </p>
            </div>
          </section>

          {/* 2. Datos */}
          <section id="datos">
            <h2 className="font-display text-2xl font-bold mb-3">
              2. Datos que recopilamos
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>Recopilamos los siguientes tipos de datos:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">Datos del CV:</strong> nombre,
                  correo electrónico, teléfono, ubicación, historial laboral,
                  formación académica, habilidades, idiomas y foto (si está
                  incluida en el PDF).
                </li>
                <li>
                  <strong className="text-foreground">Datos de cuenta:</strong>{" "}
                  dirección de correo electrónico y datos de autenticación
                  (proporcionados a través de tu cuenta de Google OAuth).
                </li>
                <li>
                  <strong className="text-foreground">Consultas de empleo:</strong>{" "}
                  palabras clave, ubicación y filtros aplicados en las búsquedas.
                </li>
                <li>
                  <strong className="text-foreground">Datos de uso:</strong>{" "}
                  páginas visitadas, interacciones con la plataforma y metadata
                  técnica (dirección IP, navegador, timestamps).
                </li>
                <li>
                  <strong className="text-foreground">Datos de empleadores:</strong>{" "}
                  información pública de ofertas de empleo obtenidas de LinkedIn,
                  Indeed e InfoJobs.
                </li>
              </ul>
              <p>
                <strong className="text-foreground">Importante:</strong> No
                recopilamos datos de salud, orientación religiosa, orientación
                sexual, origen racial o étnico, ni opiniones políticas a través
                de la plataforma.
              </p>
            </div>
          </section>

          {/* 3. Finalidad */}
          <section id="finalidad">
            <h2 className="font-display text-2xl font-bold mb-3">
              3. Finalidad del tratamiento
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>Utilizamos tus datos para los siguientes fines:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">Generación de CV adaptado:</strong>{" "}
                  procesar tu CV (PDF) junto con la descripción de una oferta de
                  empleo para generar una versión adaptada usando inteligencia
                  artificial (Groq, EE.UU.).
                </li>
                <li>
                  <strong className="text-foreground">Búsqueda de empleo:</strong>{" "}
                  mostrarte resultados de empleo agregados de múltiples fuentes
                  (LinkedIn, Indeed, InfoJobs).
                </li>
                <li>
                  <strong className="text-foreground">Almacenamiento de CV:</strong>{" "}
                  guardar tu CV de forma segura en Supabase para reutilizarlo en
                  futuras adaptaciones.
                </li>
                <li>
                  <strong className="text-foreground">Autenticación:</strong>{" "}
                  gestionar tu cuenta e inicio de sesión a través de Google
                  OAuth.
                </li>
                <li>
                  <strong className="text-foreground">Mejora del servicio:</strong>{" "}
                  analizar el uso de la plataforma para mejorar la experiencia
                  del usuario.
                </li>
              </ul>
            </div>
          </section>

          {/* 4. Base legal */}
          <section id="base-legal">
            <h2 className="font-display text-2xl font-bold mb-3">
              4. Base legal para el tratamiento
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                El tratamiento de tus datos se realiza bajo las siguientes bases
                legales:
              </p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">Consentimiento (Art. 6(1)(a)
                  RGPD / Art. 7 LGPD):</strong> es la base legal principal. Al
                  subir tu CV y solicitar la generación de un CV adaptado,
                  das tu consentimiento explícito para que procesemos tu CV a
                  través de nuestro proveedor de IA (Groq) en Estados Unidos.
                  Este consentimiento es freely given, specific, informed y
                  unambiguous.
                </li>
                <li>
                  <strong className="text-foreground">Ejecución de un contrato
                  (Art. 6(1)(b) RGPD):</strong> para prestar el servicio de
                  búsqueda y adaptación de CV que solicitas.
                </li>
                <li>
                  <strong className="text-foreground">Interés legítimo
                  (Art. 6(1)(f) RGPD):</strong> para mejorar la plataforma,
                  prevenir fraude y garantizar la seguridad.
                </li>
              </ul>
              <p>
                <strong className="text-foreground">Consentimiento explícito
                para Groq:</strong> antes de generar un CV adaptado, debes
                marcar una casilla de consentimiento explícito confirmando que
                comprendes y aceptas que tu CV será procesado por Groq en
                Estados Unidos. Este consentimiento es revocable en cualquier
                momento contactándonos.
              </p>
            </div>
          </section>

          {/* 5. Transferencia internacional */}
          <section id="transferencia">
            <h2 className="font-display text-2xl font-bold mb-3">
              5. Transferencia internacional de datos (EEE → EE.UU.)
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                <strong className="text-foreground">Esta es la transferencia
                más sensible bajo el RGPD y la LGPD.</strong>
              </p>
              <p>
                Cuando generas un CV adaptado, el contenido de tu CV (nombre,
                experiencia laboral, formación, habilidades, etc.) es enviado a
                <strong className="text-foreground"> Groq, Inc.</strong>, una
                empresa ubicada en{" "}
                <strong className="text-foreground">Estados Unidos de América</strong>,
                a través de su API REST compatible con OpenAI.
              </p>
              <p>Esto implica:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">Transferencia fuera del
                  EEE:</strong> tus datos personales salen del Espacio Económico
                  Europeo y son procesados en Estados Unidos.
                </li>
                <li>
                  <strong className="text-foreground">Riesgos asociados:</strong>{" "}
                  Estados Unidos no tiene, en principio, un nivel de protección
                  de datos equivalente al del EEE. Sin embargo, Groq opera bajo
                  el <em>EU-U.S. Data Privacy Framework</em> (desde julio de 2023)
                  y el <em>Data Privacy Framework</em> UE-EE.UU., lo que establece
                  un mecanismo de transferencia considerado adecuado por la Comisión
                  Europea.
                </li>
                <li>
                  <strong className="text-foreground">Procesamiento por Groq:</strong>{" "}
                  Groq procesa tus datos únicamente para generar la respuesta de
                  adaptación del CV. Según sus políticas, los datos enviados a la
                  API no se almacenan permanentemente para entrenamiento de
                  modelos. Te recomendamos revisar la{" "}
                  <a
                    href="https://console.groq.com/privacy"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    política de privacidad de Groq
                  </a>{" "}
                  para conocer sus prácticas actuales.
                </li>
                <li>
                  <strong className="text-foreground">Tus derechos:</strong> al
                  transferir datos a Groq, podrías ejercer tus derechos de
                  protección de datos frente a Groq directamente, además de
                  frente a nosotros.
                </li>
              </ul>
              <p>
                Al utilizar el servicio de generación de CV adaptado,{" "}
                <strong className="text-foreground">consientes expresamente</strong>{" "}
                esta transferencia internacional a Estados Unidos conforme al
                Art. 49(1)(a) RGPD (consentimiento explícito) y Art. 49(1)
                LGPD.
              </p>
            </div>
          </section>

          {/* 6. Retención */}
          <section id="retencion">
            <h2 className="font-display text-2xl font-bold mb-3">
              6. Retención de datos
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">CV almacenado:</strong>{" "}
                  tu CV en PDF se almacena en Supabase Storage hasta que lo
                  elimines o elimines tu cuenta. Puedes solicitar la eliminación
                  en cualquier momento.
                </li>
                <li>
                  <strong className="text-foreground">Procesamiento LLM:</strong>{" "}
                  el contenido de tu CV enviado a Groq es procesado de forma
                  transitoria. Groq no debería retener tus datos más allá de lo
                  necesario para completar la solicitud. No tenemos control
                  sobre los servidores de Groq.
                </li>
                <li>
                  <strong className="text-foreground">Datos de sesión:</strong>{" "}
                  los logs de acceso se retienen por un máximo de 30 días por
                  razones de seguridad.
                </li>
                <li>
                  <strong className="text-foreground">Datos de cuenta:</strong>{" "}
                  se retienen mientras la cuenta esté activa. Al eliminar la
                  cuenta, los datos se eliminan en un plazo máximo de 30 días,
                  salvo obligación legal de retención.
                </li>
              </ul>
            </div>
          </section>

          {/* 7. Tus derechos */}
          <section id="tus-derechos">
            <h2 className="font-display text-2xl font-bold mb-3">
              7. Tus derechos
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>Tienes los siguientes derechos sobre tus datos personales:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>
                  <strong className="text-foreground">Acceso (Art. 15 RGPD /
                  Art. 18 LGPD):</strong> obtener una copia de tus datos
                  personales que tenemos.
                </li>
                <li>
                  <strong className="text-foreground">Rectificación (Art. 16
                  RGPD / Art. 19 LGPD):</strong> corregir datos inexactos o
                  incompletos.
                </li>
                <li>
                  <strong className="text-foreground">Supresión (Art. 17 RGPD /
                  Art. 20 LGPD):</strong> solicitar la eliminación de tus datos,
                  incluso el CV almacenado.
                </li>
                <li>
                  <strong className="text-foreground">Portabilidad (Art. 20
                  RGPD / Art. 26 LGPD):</strong> recibir tus datos en un
                  formato estructurado y legible por máquina.
                </li>
                <li>
                  <strong className="text-foreground">Revocación del
                  consentimiento:</strong> en cualquier momento, revocando el
                  consentimiento para el procesamiento LLM. Esto no afecta la
                  legalidad del tratamiento previo.
                </li>
                <li>
                  <strong className="text-foreground">Oposición (Art. 21
                  RGPD):</strong> oponerte al tratamiento basado en interés
                  legítimo.
                </li>
                <li>
                  <strong className="text-foreground">Reclamación ante la
                  autoridad:</strong> presentar una queja ante la autoridad de
                  protección de datos de tu país (en España:{" "}
                  <a
                    href="https://www.aepd.es"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    AEPD
                  </a>
                  ; en Brasil:{" "}
                  <a
                    href="https://www.gov.br/anpd/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    ANPD
                  </a>
                  ).
                </li>
              </ul>
              <p>
                Para ejercer cualquiera de estos derechos, contactanos en:{" "}
                <a href="mailto:privacidad@jobsfinder.example.com" className="text-primary hover:underline">
                  privacidad@jobsfinder.example.com
                </a>
                . Responderemos en un plazo máximo de 30 días.
              </p>
            </div>
          </section>

          {/* 8. Seguridad */}
          <section id="seguridad">
            <h2 className="font-display text-2xl font-bold mb-3">
              8. Seguridad
            </h2>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                Implementamos medidas técnicas y organizativas apropiadas para
                proteger tus datos personales contra acceso no autorizado,
                pérdida, alteración o destrucción, incluyendo:
              </p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li>Cifrado en tránsito (TLS/HTTPS) para todas las comunicaciones.</li>
                <li>
                  Almacenamiento cifrado de CVs en Supabase Storage.
                </li>
                <li>
                  Control de acceso basado en roles dentro de la plataforma.
                </li>
                <li>
                  Auditoría de logs de acceso con retención de 30 días.
                </li>
                <li>
                  Autenticación mediante Google OAuth con protocolos estándar
                  de la industria.
                </li>
              </ul>
              <p>
                Ningún sistema es 100% seguro. Si detectas una brecha de
                seguridad que afecte tus datos, notifícanos inmediatamente a{" "}
                <a href="mailto:privacidad@jobsfinder.example.com" className="text-primary hover:underline">
                  privacidad@jobsfinder.example.com
                </a>
                .
              </p>
            </div>
          </section>

          {/* 9. Actualizaciones */}
          <section id="actualizaciones">
            <h2 className="font-display text-2xl font-bold mb-3">
              9. Actualizaciones de esta política
            </h2>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                Podemos actualizar esta política de privacidad periódicamente,
                especialmente si hay cambios en los servicios de Groq, en la
                legislación aplicable o en la arquitectura técnica de la
                plataforma.
              </p>
              <p>
                Los cambios se publicarán en esta misma página. Para cambios
                significativos (por ejemplo, un nuevo proveedor de IA, cambio
                en la base legal, o modificaciones que amplíen la transferencia
                internacional), te notificaremos a través de un aviso visible
                en la plataforma o por correo electrónico si tienes una cuenta
                registrada.
              </p>
              <p>
                Te recomendamos revisar esta política periódicamente. El uso
                continuado de la plataforma después de cualquier modificación
                implica la aceptación de la política actualizada.
              </p>
            </div>
          </section>

          {/* 10. Contacto */}
          <section id="contacto">
            <h2 className="font-display text-2xl font-bold mb-3">
              10. Contacto
            </h2>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                Si tienes preguntas, solicitudes o quejas relacionadas con
                esta política de privacidad o el tratamiento de tus datos
                personales, contactanos:
              </p>
              <p>
                <strong className="text-foreground">Email:</strong>{" "}
                <a href="mailto:privacidad@jobsfinder.example.com" className="text-primary hover:underline">
                  privacidad@jobsfinder.example.com
                </a>
              </p>
              <p>
                Si no estás satisfecho con nuestra respuesta, tienes derecho
                a presentar una queja ante la autoridad de protección de datos
                competente de tu jurisdicción.
              </p>
            </div>
          </section>
        </div>

        {/* Back link */}
        <div className="mt-12 pt-8 border-t">
          <Link
            href="/"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Volver a Jobs Finder
          </Link>
        </div>
      </main>

      <Footer />
    </div>
  );
}
