import Link from 'next/link'
import { MapPin, Phone, Mail, Instagram, Facebook } from 'lucide-react'

const footerLinks = [
  { href: '/pages/quienes-somos', label: 'Quiénes somos' },
  { href: '/pages/contacto', label: 'Contacto' },
  { href: '/pages/devoluciones', label: 'Política de devoluciones' },
  { href: '/pages/envio', label: 'Política de envío' },
  { href: '/pages/privacidad', label: 'Privacidad' },
  { href: '/pages/terminos', label: 'Términos y condiciones' },
]

export default function Footer() {
  return (
    <footer className="bg-brand text-white">
      {/* Trust badges */}
      <div className="border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
          <div className="flex flex-col items-center gap-2">
            <span className="text-3xl">🚀</span>
            <h3 className="font-bold text-sm uppercase tracking-wide">Envío rápido</h3>
            <p className="text-xs text-white/60">Envíos en 48–72 horas</p>
          </div>
          <div className="flex flex-col items-center gap-2">
            <span className="text-3xl">🔒</span>
            <h3 className="font-bold text-sm uppercase tracking-wide">Pago seguro</h3>
            <p className="text-xs text-white/60">Visa, Mastercard, Bizum, Apple Pay</p>
          </div>
          <div className="flex flex-col items-center gap-2">
            <span className="text-3xl">✅</span>
            <h3 className="font-bold text-sm uppercase tracking-wide">Garantía 6 meses</h3>
            <p className="text-xs text-white/60">Garantía oficial del fabricante</p>
          </div>
        </div>
      </div>

      {/* Main footer */}
      <div className="max-w-7xl mx-auto px-6 py-12 grid grid-cols-1 md:grid-cols-3 gap-10">
        {/* Brand */}
        <div className="flex flex-col gap-4">
          <h2 className="text-2xl font-black uppercase">
            Padel<span className="text-brand-accent"> Cañaveral</span>
          </h2>
          <p className="text-sm text-white/60 leading-relaxed">
            Tu tienda de pádel de confianza en Madrid. Palas, zapatillas, mochilas y pelotas de las mejores marcas.
          </p>
          <div className="flex gap-3 mt-2">
            <a href="#" className="bg-white/10 hover:bg-brand-accent p-2 rounded-full transition-colors">
              <Instagram size={16} />
            </a>
            <a href="#" className="bg-white/10 hover:bg-brand-accent p-2 rounded-full transition-colors">
              <Facebook size={16} />
            </a>
          </div>
        </div>

        {/* Links */}
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wide mb-4">Información</h3>
          <ul className="flex flex-col gap-2">
            {footerLinks.map(l => (
              <li key={l.href}>
                <Link href={l.href} className="text-sm text-white/60 hover:text-white transition-colors">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        {/* Contact */}
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wide mb-4">Visítanos</h3>
          <div className="flex flex-col gap-3 text-sm text-white/60">
            <div className="flex items-start gap-2">
              <MapPin size={15} className="mt-0.5 shrink-0 text-brand-accent" />
              <span>Calle Enrique Urquijo, 90<br />28052 El Cañaveral, Madrid</span>
            </div>
            <div className="flex items-center gap-2">
              <Phone size={15} className="shrink-0 text-brand-accent" />
              <span>744 654 674</span>
            </div>
            <div className="flex items-center gap-2">
              <Mail size={15} className="shrink-0 text-brand-accent" />
              <span>padel@padelcanaveral.com</span>
            </div>
            <div className="mt-2 text-xs">
              <p>Lunes a Viernes: 10:00–14:00 y 16:30–20:30</p>
              <p>Sábados: 10:00–14:00</p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div className="border-t border-white/10 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-white/40">
          <span>© 2026 Padel Cañaveral · Todos los derechos reservados</span>
          <span>Demo creada con Next.js · Solo para pruebas</span>
        </div>
      </div>
    </footer>
  )
}
