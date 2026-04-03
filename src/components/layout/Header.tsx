'use client'
import { useState } from 'react'
import Link from 'next/link'
import { ShoppingCart, Search, Menu, X, MapPin, Phone, Mail } from 'lucide-react'

const navLinks = [
  { href: '/collections/palas-2026', label: 'Palas 2026' },
  { href: '/collections/palas-2025', label: 'Palas 2025' },
  { href: '/collections/zapatillas', label: 'Zapatillas' },
  { href: '/collections/mochilas', label: 'Mochilas' },
  { href: '/collections/pelotas', label: 'Pelotas' },
]

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="w-full sticky top-0 z-50 shadow-md">
      {/* Top bar */}
      <div className="bg-brand-accent text-white text-sm py-2 px-4 text-center font-medium tracking-wide">
        🚀 ENVÍO GRATIS EN PEDIDOS +75€ &nbsp;|&nbsp; 📍 Tienda física: Calle Enrique Urquijo, 90 · El Cañaveral, Madrid
      </div>

      {/* Main nav */}
      <nav className="bg-brand text-white px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/" className="text-2xl font-black tracking-tight uppercase shrink-0">
            <span className="text-white">Padel</span>
            <span className="text-brand-accent"> Cañaveral</span>
          </Link>

          {/* Desktop links */}
          <ul className="hidden md:flex items-center gap-6 text-sm font-semibold uppercase tracking-wide">
            {navLinks.map(l => (
              <li key={l.href}>
                <Link href={l.href} className="hover:text-brand-accent transition-colors">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>

          {/* Icons */}
          <div className="flex items-center gap-4">
            <button className="hidden md:block hover:text-brand-accent transition-colors">
              <Search size={20} />
            </button>
            <Link href="/cart" className="relative hover:text-brand-accent transition-colors">
              <ShoppingCart size={22} />
              <span className="absolute -top-2 -right-2 bg-brand-accent text-white text-xs rounded-full w-4 h-4 flex items-center justify-center font-bold">0</span>
            </Link>
            <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)}>
              {menuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div className="md:hidden mt-4 border-t border-white/20 pt-4 pb-2 flex flex-col gap-3">
            {navLinks.map(l => (
              <Link
                key={l.href}
                href={l.href}
                className="text-sm font-semibold uppercase tracking-wide hover:text-brand-accent px-2"
                onClick={() => setMenuOpen(false)}
              >
                {l.label}
              </Link>
            ))}
          </div>
        )}
      </nav>
    </header>
  )
}
