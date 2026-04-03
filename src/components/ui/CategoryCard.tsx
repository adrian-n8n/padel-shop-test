import Link from 'next/link'
import { Category } from '@/data/products'

type Props = { category: Category }

export default function CategoryCard({ category }: Props) {
  return (
    <Link
      href={`/collections/${category.slug}`}
      className="group relative rounded-2xl overflow-hidden aspect-[4/3] flex items-end shadow-md hover:shadow-2xl transition-all duration-300"
    >
      <div
        className="absolute inset-0 bg-gradient-to-br from-brand to-brand-light group-hover:scale-105 transition-transform duration-500"
        style={{ backgroundImage: `url(${category.image})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
      <div className="relative p-5 w-full">
        <h3 className="text-white font-black text-xl uppercase tracking-tight">{category.name}</h3>
        <p className="text-white/70 text-sm mt-1">{category.description}</p>
        <span className="inline-block mt-3 text-xs font-bold uppercase tracking-wider text-brand-accent border border-brand-accent px-3 py-1 rounded-full
          group-hover:bg-brand-accent group-hover:text-white transition-colors">
          Ver todo →
        </span>
      </div>
    </Link>
  )
}
