import Link from 'next/link'
import HeroBanner from '@/components/ui/HeroBanner'
import ProductCard from '@/components/ui/ProductCard'
import CategoryCard from '@/components/ui/CategoryCard'
import NewsletterForm from '@/components/ui/NewsletterForm'
import { getTopSelling, getFeaturedProducts, categories } from '@/data/products'

const players = [
  { name: 'Ale Galán', slug: 'ale-galan', emoji: '🏆' },
  { name: 'Agustín Tapia', slug: 'tapia', emoji: '⚡' },
  { name: 'Juan Lebrón', slug: 'lebron', emoji: '🎯' },
  { name: 'Arturo Coello', slug: 'coello', emoji: '🔥' },
  { name: 'Paquito Navarro', slug: 'paquito', emoji: '💪' },
  { name: 'Franco Stupa', slug: 'stupa', emoji: '🚀' },
  { name: 'Marta Ortega', slug: 'marta', emoji: '⭐' },
  { name: 'Ale Ruiz', slug: 'ale-ruiz', emoji: '🎾' },
]

export default function Home() {
  const topSelling = getTopSelling()
  const featured = getFeaturedProducts()

  return (
    <>
      {/* Hero */}
      <HeroBanner />

      {/* Top selling */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <p className="text-brand-accent text-sm font-bold uppercase tracking-widest mb-1">Más populares</p>
            <h2 className="text-3xl font-black uppercase text-brand">Las más vendidas</h2>
          </div>
          <Link href="/collections/palas" className="text-sm font-bold text-brand hover:text-brand-accent transition-colors hidden sm:block">
            Ver todas →
          </Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
          {topSelling.map(p => <ProductCard key={p.id} product={p} />)}
        </div>
      </section>

      {/* Categories */}
      <section className="bg-white py-16">
        <div className="max-w-7xl mx-auto px-6">
          <div className="mb-8">
            <p className="text-brand-accent text-sm font-bold uppercase tracking-widest mb-1">Navega por</p>
            <h2 className="text-3xl font-black uppercase text-brand">Categorías</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {categories.map(cat => <CategoryCard key={cat.slug} category={cat} />)}
          </div>
        </div>
      </section>

      {/* Players */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="mb-8">
          <p className="text-brand-accent text-sm font-bold uppercase tracking-widest mb-1">Colecciones</p>
          <h2 className="text-3xl font-black uppercase text-brand">Juega como los profesionales</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          {players.map(p => (
            <Link
              key={p.slug}
              href={`/collections/${p.slug}`}
              className="bg-white rounded-xl p-4 flex flex-col items-center gap-2 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200 text-center group"
            >
              <span className="text-3xl">{p.emoji}</span>
              <span className="text-xs font-bold text-brand group-hover:text-brand-accent transition-colors leading-tight">
                {p.name}
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* Sales banner */}
      <section className="bg-brand-accent text-white py-14">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h2 className="text-3xl md:text-4xl font-black uppercase">Hasta 52% de descuento</h2>
            <p className="text-white/80 mt-2 text-lg">Liquidación palas temporada 2025. ¡Últimas unidades!</p>
          </div>
          <Link
            href="/collections/palas-2025"
            className="shrink-0 bg-white text-brand-accent font-black uppercase px-8 py-4 rounded-full text-sm tracking-widest hover:scale-105 transition-transform"
          >
            Ver ofertas
          </Link>
        </div>
      </section>

      {/* Featured */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <p className="text-brand-accent text-sm font-bold uppercase tracking-widest mb-1">Novedades y ofertas</p>
            <h2 className="text-3xl font-black uppercase text-brand">Palas 2026</h2>
          </div>
          <Link href="/collections/palas" className="text-sm font-bold text-brand hover:text-brand-accent transition-colors hidden sm:block">
            Ver todas →
          </Link>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {featured.map(p => <ProductCard key={p.id} product={p} />)}
        </div>
      </section>

      {/* Newsletter */}
      <section className="bg-brand text-white py-14">
        <div className="max-w-lg mx-auto px-6 text-center">
          <h2 className="text-2xl font-black uppercase mb-2">Suscríbete y ahorra</h2>
          <p className="text-white/60 mb-6 text-sm">Descuentos exclusivos, novedades y ofertas solo para suscriptores.</p>
          <NewsletterForm />
        </div>
      </section>
    </>
  )
}
