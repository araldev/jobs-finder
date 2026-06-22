/**
 * @deprecated Since slice 5 of `feat-frontend-i18n`. The strings in this
 * file have been migrated to `messages/{en,es}.json` under the
 * `Auth.*` and `Validation.*` namespaces, and every consumer (the 4
 * auth forms, the 3 settings forms, the Zod schemas) now reads via
 * `useTranslations('Auth')` / `useTranslations('Validation')`.
 *
 * This file is kept ONLY so any straggler test that imports it still
 * resolves at module-load time during the in-between state. Slice 15
 * will delete it entirely.
 *
 * New code MUST NOT import from here — use `useTranslations` instead.
 */
export const authCopy = Object.freeze({
  forgot: Object.freeze({
    title: "Recuperar contraseña",
    subtitle: "Te enviaremos un enlace para restablecer tu contraseña.",
    emailLabel: "Email",
    submit: "Enviar enlace de recuperación",
    successTitle: "Revisa tu correo",
    successDescription:
      "Si la dirección está registrada, recibirás un enlace para restablecer tu contraseña en los próximos minutos.",
    backToLogin: "Volver a iniciar sesión",
  }),
  reset: Object.freeze({
    invalidLinkTitle: "El enlace no es válido o ha expirado",
    invalidLinkDescription:
      "Por seguridad, los enlaces de recuperación expiran después de un tiempo. Solicitá uno nuevo.",
    resendLink: "Volver a solicitar",
    title: "Restablecer contraseña",
    subtitle: "Ingresá tu nueva contraseña.",
    newPasswordLabel: "Nueva contraseña",
    confirmPasswordLabel: "Confirmar contraseña",
    submit: "Actualizar contraseña",
    successToast: "Contraseña actualizada",
  }),
  change: Object.freeze({
    title: "Cambiar contraseña",
    subtitle: "Rotá tu contraseña sin cerrar sesión.",
    currentPasswordLabel: "Contraseña actual",
    newPasswordLabel: "Nueva contraseña",
    confirmPasswordLabel: "Confirmar nueva contraseña",
    submit: "Cambiar contraseña",
    successToast: "Contraseña actualizada",
    wrongCurrentToast: "Contraseña actual incorrecta",
    oauthToast: "Iniciaste sesión con un proveedor externo. No tenés contraseña para cambiar.",
  }),
  delete: Object.freeze({
    title: "Eliminar cuenta",
    subtitle: "Esta acción es permanente y no se puede deshacer.",
    destructiveHelp:
      "Se eliminarán tu cuenta, tu CV y todos los datos asociados. Esta acción es irreversible.",
    triggerLabel: "Eliminar cuenta",
    confirmTitle: "¿Eliminar tu cuenta para siempre?",
    confirmDescription:
      "Esta acción es permanente. Se borrarán tu CV, tus favoritos y todos los datos asociados.",
    confirmEmailLabel: "Confirmá con tu correo electrónico",
    confirmPlaceholder: "tu@email.com",
    confirmSubmit: "Sí, eliminar mi cuenta",
    confirmCancel: "Cancelar",
    errorToast:
      "No pudimos eliminar tu cuenta. Intentalo de nuevo o contactá soporte.",
    successToast: "Tu cuenta fue eliminada.",
  }),
  banner: Object.freeze({
    title: "Verificá tu correo",
    description:
      "Te enviamos un enlace de verificación. Confirmalo para acceder a todas las funciones.",
    resend: "Reenviar email",
    resendToast: "Correo reenviado",
    resendErrorToast:
      "No pudimos reenviar el correo. Intentalo de nuevo en unos minutos.",
    dismiss: "Descartar",
  }),
  magicLink: Object.freeze({
    title: "Enlace mágico",
    subtitle: "Te enviaremos un enlace para iniciar sesión sin contraseña.",
    submit: "Enviar enlace mágico",
    successTitle: "Revisa tu correo",
    successDescription:
      "Te enviamos un enlace para iniciar sesión. Abrilo desde este navegador.",
  }),
  globalSignOut: Object.freeze({
    triggerLabel: "Cerrar sesión en todos los dispositivos",
    tooltip:
      "Cerraremos tu sesión en otros dispositivos. Las sesiones ya iniciadas pueden tardar hasta 1 hora en expirar.",
    confirmTitle: "¿Cerrar sesión en todos los dispositivos?",
    confirmDescription:
      "Cerraremos tu sesión activa en este navegador y revocaremos las sesiones en otros dispositivos. Deberás volver a iniciar sesión.",
    confirmSubmit: "Sí, cerrar sesión",
    confirmCancel: "Cancelar",
    errorToast: "No pudimos cerrar las sesiones. Intentalo de nuevo.",
  }),
  validation: Object.freeze({
    emailRequired: "Ingresá tu correo electrónico",
    emailInvalid: "Ingresá un correo válido",
    passwordRequired: "Ingresá tu contraseña",
    passwordMinLength: "Mínimo 6 caracteres",
    passwordsDoNotMatch: "Las contraseñas no coinciden",
    passwordMustDiffer: "La nueva contraseña debe ser distinta de la actual",
    deleteEmailMismatch: "Escribí tu correo exacto para confirmar",
  }),
  toast: Object.freeze({
    networkError: "No pudimos enviar el correo. Intentalo de nuevo.",
    rateLimit: "Demasiados intentos. Esperá unos minutos antes de volver a intentar.",
    genericError: "Ocurrió un error. Intentalo de nuevo.",
  }),
});

export type AuthCopy = typeof authCopy;