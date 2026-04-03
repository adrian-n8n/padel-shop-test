/**
 * Antepone el basePath de Next.js a rutas locales (que empiezan por /).
 * Las URLs absolutas (http/https) se devuelven sin cambios.
 * Necesario para next/image con output:'export' + basePath en GitHub Pages.
 */
export function imgSrc(src: string): string {
  if (!src) return ''
  if (src.startsWith('http://') || src.startsWith('https://')) return src
  const base = process.env.NEXT_PUBLIC_BASE_PATH ?? ''
  return `${base}${src}`
}
