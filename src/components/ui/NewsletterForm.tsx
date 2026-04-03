'use client'

export default function NewsletterForm() {
  return (
    <form className="flex gap-2" onSubmit={e => e.preventDefault()}>
      <input
        type="email"
        placeholder="tu@email.com"
        className="flex-1 rounded-full px-5 py-3 text-sm text-gray-900 outline-none focus:ring-2 focus:ring-brand-accent"
      />
      <button
        type="submit"
        className="bg-brand-accent text-white px-6 py-3 rounded-full text-sm font-bold uppercase tracking-wide hover:bg-red-600 transition-colors"
      >
        Suscribir
      </button>
    </form>
  )
}
