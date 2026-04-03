import Link from 'next/link'
import ProductCard from '@/components/ui/ProductCard'
import { products, categories } from '@/data/products'

// Mapa de slugs de jugadores → palabras clave a buscar en nombre/marca
const playerKeywords: Record<string, string[]> = {
  'ale-galan':  ['galán', 'galan', 'metalbone'],
  'tapia':      ['tapia', 'at10', 'at12'],
  'lebron':     ['lebrón', 'lebron'],
  'coello':     ['coello'],
  'paquito':    ['paquito', 'navarro'],
  'stupa':      ['stupa'],
  'marta':      ['marta ortega', 'marta'],
  'ale-ruiz':   ['ale ruiz', 'alejandra ruiz'],
}

function getProductsForSlug(slug: string) {
  // Categoría exacta (palas, zapatillas, etc.)
  const byCategory = products.filter(p => p.category === slug)
  if (byCategory.length > 0) return byCategory

  // Jugador → buscar por keywords en nombre
  const keywords = playerKeywords[slug]
  if (keywords) {
    return products.filter(p => {
      const lower = p.name.toLowerCase()
      return keywords.some(k => lower.includes(k))
    })
  }

  // Fallback: buscar slug en nombre
  const byName = products.filter(p => p.name.toLowerCase().includes(slug.replace(/-/g, ' ')))
  return byName
}

export async function generateStaticParams() {
  const categorySlugs = categories.map(c => ({ slug: c.slug }))
  const playerSlugs = Object.keys(playerKeywords).map(s => ({ slug: s }))
  return [...categorySlugs, ...playerSlugs]
}

type Props = { params: { slug: string } }

export default function CollectionPage({ params }: Props) {
  const { slug } = params
  const category = categories.find(c => c.slug === slug)
  const collectionProducts = getProductsForSlug(slug)

  const playerNames: Record<string, string> = {
    'ale-galan': 'Ale Galán', 'tapia': 'Agustín Tapia', 'lebron': 'Juan Lebrón',
    'coello': 'Arturo Coello', 'paquito': 'Paquito Navarro', 'stupa': 'Franco Stupa',
    'marta': 'Marta Ortega', 'ale-ruiz': 'Alejandra Ruiz',
  }

  const title = category?.name ?? playerNames[slug] ?? slug.replace(/-/g, ' ')
  const description = category?.description
    ?? (playerNames[slug] ? `Palas y equipamiento de ${playerNames[slug]}` : 'Colección seleccionada')

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-400 mb-6 flex gap-2">
        <Link href="/" className="hover:text-brand-accent transition-colors">Inicio</Link>
        <span>/</span>
        <span className="text-gray-700 font-medium">{title}</span>
      </nav>

      {/* Header */}
      <div className="mb-10">
        <h1 className="text-4xl font-black uppercase text-brand mb-2">{title}</h1>
        <p className="text-gray-500">{description}</p>
        {collectionProducts.length > 0 && (
          <p className="text-sm text-gray-400 mt-1">{collectionProducts.length} productos</p>
        )}
      </div>

      {/* Grid */}
      {collectionProducts.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5">
          {collectionProducts.map(p => <ProductCard key={p.id} product={p} />)}
        </div>
      ) : (
        <div className="text-center py-24 text-gray-400">
          <p className="text-5xl mb-4">🎾</p>
          <p className="text-lg font-semibold">Próximamente</p>
          <p className="text-sm mt-1">Esta colección estará disponible muy pronto.</p>
          <Link href="/" className="inline-block mt-6 bg-brand text-white px-6 py-3 rounded-full text-sm font-bold hover:bg-brand-accent transition-colors">
            Volver al inicio
          </Link>
        </div>
      )}
    </div>
  )
}

