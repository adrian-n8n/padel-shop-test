import Link from 'next/link'
import { getProductBySlug, products } from '@/data/products'
import { notFound } from 'next/navigation'
import { ShoppingCart, Truck, Shield, RotateCcw } from 'lucide-react'
import ProductGallery from '@/components/ui/ProductGallery'

export async function generateStaticParams() {
  return products.map(p => ({ slug: p.slug }))
}

type Props = { params: { slug: string } }

export default function ProductPage({ params }: Props) {
  const product = getProductBySlug(params.slug)
  if (!product) notFound()

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-400 mb-8 flex gap-2 flex-wrap">
        <Link href="/" className="hover:text-brand-accent transition-colors">Inicio</Link>
        <span>/</span>
        <Link href={`/collections/${product.category}`} className="hover:text-brand-accent transition-colors capitalize">
          {product.category.replace(/-/g, ' ')}
        </Link>
        <span>/</span>
        <span className="text-gray-700 font-medium line-clamp-1">{product.name}</span>
      </nav>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
        {/* Gallery */}
        <ProductGallery
          images={product.images ?? [product.image]}
          name={product.name}
          badge={product.discount ? `-${product.discount}%` : null}
        />

        {/* Info */}
        <div className="flex flex-col gap-5">
          <div>
            <span className="text-brand-accent text-sm font-black uppercase tracking-widest">{product.brand}</span>
            <h1 className="text-3xl font-black text-brand mt-2 leading-tight">{product.name}</h1>
          </div>

          {/* Price */}
          <div className="flex items-center gap-4">
            <span className="text-4xl font-black text-gray-900">
              {product.price.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
            </span>
            {product.originalPrice && (
              <>
                <span className="text-xl text-gray-400 line-through">
                  {product.originalPrice.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
                </span>
                <span className="bg-brand-accent/10 text-brand-accent text-sm font-bold px-3 py-1 rounded-full">
                  Ahorras {(product.originalPrice - product.price).toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
                </span>
              </>
            )}
          </div>

          {/* Description */}
          <p className="text-gray-600 leading-relaxed">{product.description}</p>

          {/* CTA */}
          <div className="flex flex-col gap-3 mt-2">
            <button className="w-full bg-brand-accent text-white py-4 rounded-full font-black uppercase text-sm tracking-widest hover:bg-red-600 transition-colors flex items-center justify-center gap-2">
              <ShoppingCart size={18} />
              Añadir al carrito
            </button>
            <button className="w-full border-2 border-brand text-brand py-4 rounded-full font-black uppercase text-sm tracking-widest hover:bg-brand hover:text-white transition-colors">
              Comprar ahora
            </button>
          </div>

          {/* Guarantees */}
          <div className="border-t pt-6 grid grid-cols-3 gap-4 text-center">
            <div className="flex flex-col items-center gap-1">
              <Truck size={20} className="text-brand-accent" />
              <span className="text-xs font-semibold text-gray-600">Envío 48–72h</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <Shield size={20} className="text-brand-accent" />
              <span className="text-xs font-semibold text-gray-600">Garantía 6 meses</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <RotateCcw size={20} className="text-brand-accent" />
              <span className="text-xs font-semibold text-gray-600">Devoluciones fáciles</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
