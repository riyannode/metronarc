export default function Evidence() {
  return (
    <section id="evidence" aria-label="METRON editorial image" className="relative overflow-hidden bg-white">
      <img
        src="/images/metron-editorial.webp"
        alt="An empty studio with vintage computer screens and research notes"
        width={1672}
        height={941}
        loading="lazy"
        decoding="async"
        className="editorial-image block aspect-video w-full object-cover"
      />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_bottom,#fff,transparent_8%,transparent_92%,#fff)]" />
    </section>
  )
}
