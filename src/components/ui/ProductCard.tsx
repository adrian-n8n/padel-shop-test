import Link from 'next/link'
import Image from 'next/image'
import { Product } from '@/data/products'

type Props = { product: Product }

export default function ProductCard({ product }: Props) {
  const hasDiscount = product.discount && product.originalPrice

  return (
    <Link
      href={`/product/${product.slug}`}
      className="group bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col"
    >
      {/* Image */}
      <div className="relative aspect-square bg-gray-50 overflow-hidden">
        <Image
          src={product.image}
          alt={product.name}
          fill
          className="object-cover group-hover:scale-105 transition-transform duration-500"
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
        />
        {/* Badges */}
        <div className="absolute top-3 left-3 flex flex-col gap-1">
          {product.discount && (
            <span className="bg-brand-accent text-white text-xs font-bold px-2 py-1 rounded-full">
              -{product.discount}%
            </span>
          )}
          {!product.discount && (
            <span className="bg-brand text-white text-xs font-bold px-2 py-1 rounded-full">
              NUEVO
            </span>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="p-4 flex flex-col gap-1 flex-1">
        <span className="text-xs font-bold text-brand-accent uppercase tracking-wider">
          {product.brand}
        </span>
        <h3 className="text-sm font-semibold text-gray-900 leading-snug line-clamp-2 group-hover:text-brand-accent transition-colors">
          {product.name}
        </h3>
        <div className="flex items-center gap-2 mt-auto pt-3">
          <span className="text-lg font-black text-gray-900">
            {product.price.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
          </span>
          {hasDiscount && (
            <span className="text-sm text-gray-400 line-through">
              {product.originalPrice!.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
            </span>
          )}
        </div>
      </div>

      {/* CTA */}
      <div className="px-4 pb-4">
        <div className="w-full bg-brand text-white text-sm font-bold py-2.5 rounded-xl text-center
          group-hover:bg-brand-accent transition-colors duration-300">
          Añadir al carrito
        </div>
      </div>
    </Link>
  )
}
