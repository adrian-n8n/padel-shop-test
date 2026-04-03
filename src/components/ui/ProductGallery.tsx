'use client'

import { useState, useEffect, useCallback } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight, X, ZoomIn } from 'lucide-react'
import { imgSrc } from '@/lib/image'

type Props = {
  images: string[]
  name: string
  badge?: string | null
}

export default function ProductGallery({ images, name, badge }: Props) {
  const [active, setActive] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [lightboxIdx, setLightboxIdx] = useState(0)

  const all = images.length > 0 ? images : ['/images/placeholder.jpg']

  const prev = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation()
    setActive(i => (i - 1 + all.length) % all.length)
  }, [all.length])

  const next = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation()
    setActive(i => (i + 1) % all.length)
  }, [all.length])

  const openLightbox = (idx: number) => {
    setLightboxIdx(idx)
    setLightbox(true)
  }

  const prevLb = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation()
    setLightboxIdx(i => (i - 1 + all.length) % all.length)
  }, [all.length])

  const nextLb = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation()
    setLightboxIdx(i => (i + 1) % all.length)
  }, [all.length])

  // Keyboard navigation
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft')  prevLb()
      if (e.key === 'ArrowRight') nextLb()
      if (e.key === 'Escape')     setLightbox(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [lightbox, prevLb, nextLb])

  // Lock scroll when lightbox open
  useEffect(() => {
    document.body.style.overflow = lightbox ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [lightbox])

  return (
    <>
      {/* ── Main Gallery ──────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        {/* Big image */}
        <div className="relative aspect-square rounded-3xl overflow-hidden bg-gray-50 shadow-lg group cursor-zoom-in"
          onClick={() => openLightbox(active)}>
          <Image
            key={all[active]}
            src={imgSrc(all[active])}
            alt={`${name} - imagen ${active + 1}`}
            fill
            className="object-cover transition-opacity duration-300"
            sizes="(max-width: 768px) 100vw, 50vw"
            priority={active === 0}
          />
          {/* Badge */}
          {badge && (
            <span className="absolute top-4 left-4 bg-brand-accent text-white text-sm font-black px-4 py-1.5 rounded-full z-10">
              {badge}
            </span>
          )}
          {/* Zoom hint */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
            <ZoomIn size={32} className="text-white opacity-0 group-hover:opacity-80 transition-opacity drop-shadow-lg" />
          </div>
          {/* Prev/Next arrows (only if >1 image) */}
          {all.length > 1 && (
            <>
              <button onClick={prev}
                className="absolute left-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/80 hover:bg-white shadow flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 z-10">
                <ChevronLeft size={18} />
              </button>
              <button onClick={next}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-white/80 hover:bg-white shadow flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 z-10">
                <ChevronRight size={18} />
              </button>
            </>
          )}
          {/* Counter */}
          {all.length > 1 && (
            <span className="absolute bottom-3 right-4 bg-black/50 text-white text-xs font-semibold px-2.5 py-1 rounded-full z-10">
              {active + 1} / {all.length}
            </span>
          )}
        </div>

        {/* Thumbnails strip */}
        {all.length > 1 && (
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
            {all.map((src, i) => (
              <button
                key={i}
                onClick={() => setActive(i)}
                className={`relative flex-shrink-0 w-16 h-16 rounded-xl overflow-hidden border-2 transition-all
                  ${i === active
                    ? 'border-brand-accent shadow-md scale-105'
                    : 'border-transparent opacity-60 hover:opacity-100 hover:border-gray-300'}`}
              >
                <Image
                  src={imgSrc(src)}
                  alt={`${name} miniatura ${i + 1}`}
                  fill
                  className="object-cover"
                  sizes="64px"
                />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Lightbox ──────────────────────────────────────── */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center"
          onClick={() => setLightbox(false)}
        >
          {/* Close */}
          <button
            onClick={() => setLightbox(false)}
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors z-10"
          >
            <X size={20} />
          </button>

          {/* Counter */}
          <span className="absolute top-4 left-1/2 -translate-x-1/2 text-white/60 text-sm font-medium z-10">
            {lightboxIdx + 1} / {all.length}
          </span>

          {/* Prev */}
          {all.length > 1 && (
            <button onClick={prevLb}
              className="absolute left-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/10 hover:bg-white/25 text-white flex items-center justify-center transition-colors z-10">
              <ChevronLeft size={24} />
            </button>
          )}

          {/* Image */}
          <div
            className="relative w-full max-w-3xl aspect-square mx-16"
            onClick={e => e.stopPropagation()}
          >
            <Image
              key={all[lightboxIdx]}
              src={imgSrc(all[lightboxIdx])}
              alt={`${name} - imagen ${lightboxIdx + 1}`}
              fill
              className="object-contain"
              sizes="(max-width: 1024px) 100vw, 768px"
              priority
            />
          </div>

          {/* Next */}
          {all.length > 1 && (
            <button onClick={nextLb}
              className="absolute right-4 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/10 hover:bg-white/25 text-white flex items-center justify-center transition-colors z-10">
              <ChevronRight size={24} />
            </button>
          )}

          {/* Thumbnails row */}
          {all.length > 1 && (
            <div className="absolute bottom-6 left-0 right-0 flex justify-center gap-2 px-4 overflow-x-auto"
              onClick={e => e.stopPropagation()}>
              {all.map((src, i) => (
                <button
                  key={i}
                  onClick={() => setLightboxIdx(i)}
                  className={`relative flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden border-2 transition-all
                    ${i === lightboxIdx
                      ? 'border-white scale-110'
                      : 'border-white/20 opacity-50 hover:opacity-80'}`}
                >
                  <Image src={imgSrc(src)} alt="" fill className="object-cover" sizes="56px" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  )
}
