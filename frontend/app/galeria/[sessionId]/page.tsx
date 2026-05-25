// Server Component
import Image from "next/image";
import { getGallery } from "@/lib/api";
import { notFound } from "next/navigation";

export default async function GaleriaPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;

  let session: Awaited<ReturnType<typeof getGallery>>;
  try {
    session = await getGallery(sessionId);
  } catch {
    notFound();
  }

  const formattedDate = new Date(session.created_at).toLocaleString("pt-BR", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
  const videos = session.videos?.length
    ? session.videos
    : session.video_urls.map((url, index) => ({
      cabine_id: index + 1,
      video_url: url,
      qr_url: "",
    }));

  return (
    <div className="relative min-h-screen bg-[#0A0A0A] text-white font-body overflow-x-hidden">

      {/* ── BACKGROUND ───────────────────────────────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none select-none z-0" aria-hidden>
        {/* textura */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/bg-texture.jpg" alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-[0.10]"
        />
        {/* gradiente hero */}
        <div className="absolute inset-0"
          style={{ background: "linear-gradient(180deg, rgba(0,59,122,0.5) 0%, rgba(0,45,94,0.2) 30%, transparent 60%)" }}
        />
        {/* listras diagonais */}
        <div className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage: "repeating-linear-gradient(-45deg, #FFD200 0, #FFD200 1px, transparent 0, transparent 40px)",
            backgroundSize: "56px 56px",
          }}
        />
        {/* vinheta */}
        <div className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse 100% 80% at 50% 0%, transparent 50%, rgba(0,0,0,0.5) 100%)" }}
        />
      </div>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <header className="relative z-10 px-5 pt-10 pb-8">
        {/* logos */}
        <div className="flex items-center justify-center gap-4 mb-7">
          <Image src="/Hellmanns-Logo.png" alt="Hellmann's" width={44} height={44}
            className="object-contain drop-shadow-[0_0_12px_rgba(255,210,0,0.3)]" />
          <span className="font-display text-[#FFD200] text-3xl leading-none drop-shadow-[0_0_16px_rgba(255,210,0,0.5)]">×</span>
          <Image src="/National-Basketball-Association-Logo.png" alt="NBA" width={36} height={44} className="object-contain" />
        </div>

        {/* supertítulo */}
        <p className="text-center text-white/25 font-body text-[9px] tracking-[0.45em] uppercase mb-2">
          NBA HOUSE BRASIL
        </p>

        {/* título principal */}
        <div className="text-center space-y-0">
          <h1 className="font-display text-[3.6rem] leading-[0.85] tracking-wider text-[#FFD200]
                         drop-shadow-[0_0_40px_rgba(255,210,0,0.35)]">
            BAZUCA
          </h1>
          <h1 className="font-display text-[3.6rem] leading-[0.85] tracking-wider text-white">
            DE BOLINHAS
          </h1>
        </div>

        {/* divisor amarelo */}
        <div className="flex items-center gap-3 mt-6 mb-5 px-2">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#FFD200]/40" />
          <div className="h-1.5 w-10 bg-[#FFD200] rounded-full shadow-[0_0_12px_rgba(255,210,0,0.5)]" />
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#FFD200]/40" />
        </div>

        {/* badges com nomes */}
        {session.participants.length > 0 && (
          <div className="flex flex-wrap justify-center gap-2">
            {session.participants.map((name, i) => (
              <span key={i}
                className="inline-flex items-center gap-2 bg-[#FFD200]/10 border border-[#FFD200]/25
                           text-[#FFD200] font-display tracking-wider text-base px-4 py-1.5 rounded-full
                           shadow-[0_0_16px_rgba(255,210,0,0.08)]"
              >
                <span className="w-4 h-4 rounded-full bg-[#FFD200]/20 flex items-center justify-center
                                 text-[8px] text-[#FFD200]/70 font-display leading-none">
                  {i + 1}
                </span>
                {name.toUpperCase()}
              </span>
            ))}
          </div>
        )}
        <div className="flex justify-center mt-6">
          <a
            href="/operador"
            className="inline-flex items-center justify-center rounded-2xl bg-[#FFD200] px-8 py-4 font-display text-2xl tracking-[0.15em] text-[#0A0A0A]
                       shadow-[0_0_35px_rgba(255,210,0,0.25)] transition-all duration-150 hover:bg-[#ffe033] active:scale-95"
          >
            NOVA SESSÃO
          </a>
        </div>

        {/* QR Genérico — aponta para /meu-video */}
        <div className="flex flex-col items-center gap-4 mt-6 p-5 rounded-3xl bg-white/[0.04] border border-white/10">
          <p className="font-display text-[#FFD200] text-lg tracking-wider leading-none text-center">
            ESCANEIE PARA VER SEU VÍDEO
          </p>
          <p className="text-white/35 text-xs font-body text-center max-w-[200px]">
            Abra a câmera frontal e encontre seu vídeo pelo rosto
          </p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${process.env.NEXT_PUBLIC_API_BASE}/meu-video/qr.svg`}
            alt="QR Code para encontrar seu vídeo"
            className="w-44 h-44 bg-white rounded-2xl p-3"
          />
          <span className="text-white/20 text-[10px] font-body uppercase tracking-widest">
            {session.indexing_status === "indexed" ? "✓ pronto para escanear" : "processando..."}
          </span>
        </div>
      </header>

      {/* ── VÍDEOS ───────────────────────────────────────────────────────────── */}
      <main className="relative z-10 grid grid-cols-1 gap-6 px-4 pb-8 max-w-[1500px] mx-auto md:grid-cols-2 xl:grid-cols-3">
        {videos.map((video, i) => {
          const participantName = session.participants[video.cabine_id - 1] ?? session.participants[i];

          return (
          <article key={`${video.cabine_id}-${video.video_url}`}
            className="rounded-3xl overflow-hidden bg-white/[0.04] border border-white/10
                       shadow-[0_12px_64px_rgba(0,0,0,0.7)]"
          >
            {/* header do card */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10
                            bg-gradient-to-r from-[#003B7A]/40 to-transparent">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E8003D] opacity-50" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-[#E8003D]" />
                </span>
                <span className="font-display text-white tracking-[0.25em] text-base leading-none">
                  CABINE {video.cabine_id}
                </span>
              </div>
              {participantName && (
                <span className="text-[#FFD200] font-display tracking-wider text-sm">
                  {participantName.toUpperCase()}
                </span>
              )}
            </div>

            {/* vídeo 9:16 */}
            <div className="relative w-full" style={{ paddingBottom: "177.78%" }}>
              <video
                src={video.video_url}
                controls
                playsInline
                preload="metadata"
                className="absolute inset-0 w-full h-full object-contain bg-black"
                aria-label={`Vídeo da Cabine ${video.cabine_id}${participantName ? ` — ${participantName}` : ""}`}
              />
            </div>

            {/* QR direto para o vídeo da cabine */}
            {video.qr_url && (
              <div className="flex flex-col items-center gap-4 px-5 py-6 text-center bg-black/35 border-t border-white/10">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={video.qr_url}
                  alt={`QR Code direto para o vídeo da Cabine ${video.cabine_id}`}
                  className="w-44 h-44 bg-white rounded-2xl p-3 lg:w-52 lg:h-52"
                />
                <div className="space-y-1">
                  <p className="font-display text-[#FFD200] text-xl tracking-wider leading-none">
                    QR DA CABINE {video.cabine_id}
                  </p>
                  <p className="font-body text-white/40 text-xs leading-snug max-w-[15rem]">
                    Escaneie para abrir direto o vídeo final em 0.60x.
                  </p>
                </div>
              </div>
            )}

            {/* botão download */}
            <a
              href={video.video_url}
              download={`bazuca-cabine${video.cabine_id}.mp4`}
              className="flex items-center justify-center gap-3 w-full bg-[#FFD200] text-[#0A0A0A]
                         font-display text-[1.6rem] tracking-[0.15em] py-5
                         hover:bg-[#ffe033] active:scale-[0.98]
                         transition-all duration-150 uppercase"
            >
              BAIXAR VÍDEO
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0" aria-hidden>
                <path fillRule="evenodd"
                  d="M10 3a.75.75 0 01.75.75v7.69l2.47-2.47a.75.75 0 111.06 1.06l-3.75 3.75a.75.75 0 01-1.06 0L5.72 10.03a.75.75 0 111.06-1.06L9.25 11.44V3.75A.75.75 0 0110 3zm-6.5 13a.75.75 0 000 1.5h13a.75.75 0 000-1.5h-13z"
                  clipRule="evenodd" />
              </svg>
            </a>
          </article>
          );
        })}

        {videos.length === 0 && (
          <div className="text-center py-20 space-y-4">
            <div className="w-20 h-20 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-9 h-9 text-white/20">
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M15.75 10.5l4.72-2.36A1 1 0 0122 9.07v5.86a1 1 0 01-1.53.89L15.75 13.5m-9 1.5h6a2.25 2.25 0 002.25-2.25v-4.5A2.25 2.25 0 0012.75 6h-6A2.25 2.25 0 004.5 8.25v4.5A2.25 2.25 0 006.75 15z" />
              </svg>
            </div>
            <p className="text-white/25 font-body text-sm">Vídeos ainda processando...</p>
          </div>
        )}
      </main>

      {/* ── FOOTER ───────────────────────────────────────────────────────────── */}
      <footer className="relative z-10 pb-12 px-5 text-center space-y-3">
        {/* divisor */}
        <div className="flex items-center gap-3 mb-5">
          <div className="h-px flex-1 bg-white/10" />
          <div className="h-1 w-6 bg-[#FFD200]/40 rounded-full" />
          <div className="h-px flex-1 bg-white/10" />
        </div>

        {/* hashtags */}
        <p className="font-display text-[#FFD200] text-2xl tracking-wider leading-none">
          #BazucadeBolinhas
        </p>
        <p className="font-display text-white/30 text-lg tracking-wider leading-none">
          #HellmannsNBA
        </p>

        {/* timestamp */}
        <p className="font-body text-white/15 text-[10px] tracking-wider uppercase mt-4">
          {formattedDate}
        </p>

        {/* logos rodapé */}
        <div className="flex items-center justify-center gap-4 pt-3 opacity-20">
          <Image src="/Hellmanns-Logo.png" alt="" width={32} height={32} className="object-contain" />
          <span className="font-display text-white text-xl leading-none">×</span>
          <Image src="/National-Basketball-Association-Logo.png" alt="" width={24} height={32} className="object-contain" />
        </div>
      </footer>
    </div>
  );
}
