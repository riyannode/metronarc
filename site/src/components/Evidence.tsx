export default function Evidence() {
  return (
    <section id="evidence" aria-label="METRON editorial image" className="relative overflow-hidden bg-[#F5F9FF]">
      <img
        src="/images/metron-editorial.webp"
        alt="A seated man surrounded by vintage computer screens and research notes"
        width={1672}
        height={941}
        loading="lazy"
        decoding="async"
        className="editorial-image block aspect-video w-full object-cover"
      />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_bottom,#F5F9FF,transparent_16%,transparent_84%,#F5F9FF)]" />
    </section>
  )
}
