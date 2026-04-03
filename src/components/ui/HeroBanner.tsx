'use client'
import { useState } from 'react'
import Link from 'next/link'
import { ChevronLeft, ChevronRight } from 'lucide-react'

const slides = [
  {
    id: 1,
    title: '¡Ya disponible!',
    subtitle: 'Colección Babolat 2026',
    description: 'Las nuevas palas Viper Series con tecnología de carbono avanzada.',
    cta: 'Ver colección',
    href: '/collections/palas-2026',
    bg: 'from-brand to-brand-light',
    accent: '#e63946',
  },
  {
    id: 2,
    title: 'Hasta 52% descuento',
    subtitle: 'Liquidación palas 2025',
    description: 'Modelos de los mejores jugadores del mundo a precios increíbles.',
    cta: 'Aprovechar oferta',
    href: '/collections/palas-2025',
    bg: 'from-[#0d1b2a] to-[#1b4332]',
    accent: '#f4a261',
  },
  {
    id: 3,
    title: 'Envío gratis',
    subtitle: 'En pedidos superiores a 75€',
    description: 'Recibe tus palas en 48–72 horas directamente en casa.',
    cta: 'Comprar ahora',
    href: '/collections/palas-2026',
    bg: 'from-[#023047] to-[#0077b6]',
    accent: '#e63946',
  },
]

export default function HeroBanner() {
  const [current, setCurrent] = useState(0)

  const prev = () => setCurrent((c) => (c === 0 ? slides.length - 1 : c - 1))
  const next = () => setCurrent((c) => (c === slides.length - 1 ? 0 : c + 1))
  const slide = slides[current]

  return (
    <div className={`relative bg-gradient-to-r ${slide.bg} text-white overflow-hidden transition-all duration-700`}>
      <div className="max-w-7xl mx-auto px-6 py-24 md:py-36 flex flex-col gap-6 min-h-[420px] justify-center">
        <span
          className="text-sm font-bold uppercase tracking-[0.2em]"
          style={{ color: slide.accent }}
        >
          {slide.title}
        </span>
        <h1 className="text-4xl md:text-6xl font-black uppercase leading-tight max-w-xl">
          {slide.subtitle}
        </h1>
        <p className="text-white/70 text-lg max-w-md">{slide.description}</p>
        <Link
          href={slide.href}
          className="inline-block mt-2 px-8 py-3 rounded-full font-bold text-sm uppercase tracking-widest transition-all duration-300 w-fit"
          style={{ backgroundColor: slide.accent, color: '#fff' }}
        >
          {slide.cta}
        </Link>
      </div>

      {/* Controls */}
      <button
        onClick={prev}
        className="absolute left-4 top-1/2 -translate-y-1/2 bg-white/10 hover:bg-white/20 backdrop-blur p-2 rounded-full transition"
      >
        <ChevronLeft size={24} />
      </button>
      <button
        onClick={next}
        className="absolute right-4 top-1/2 -translate-y-1/2 bg-white/10 hover:bg-white/20 backdrop-blur p-2 rounded-full transition"
      >
        <ChevronRight size={24} />
      </button>

      {/* Dots */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2">
        {slides.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`w-2 h-2 rounded-full transition-all ${i === current ? 'w-6 bg-white' : 'bg-white/40'}`}
          />
        ))}
      </div>
    </div>
  )
}
