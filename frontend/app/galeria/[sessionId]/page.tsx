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

  return (
    <div className="relative min-h-screen bg-[#0A0A0A] text-white font-body overflow-x-hidden">

      {/* ── BACKGROUND ── */}
      <div className="fixed inset-0 pointer-events-none select-none z-0" aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/bg-texture.jpg" alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-[0.10]" />
        <div className="absolute inset-0"
          style={{ background: "linear-gradient(180deg, rgba(0,59,122,0.5) 0%, rgba(0,45,94,0.2) 30%, transparent 60%)" }} />
        <div className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage: "repeating-linear-gradient(-45deg, #FFD200 0, #FFD200 1px, transparent 0, transparent 40px)",
            backgroundSize: "56px 56px",
          }} />
        <div className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse 100% 80% at 50% 0%, transparent 50%, rgba(0,0,0,0.5) 100%)" }} />
      </div>

      {/* ── CONTEÚDO ── */}
      <main className="relative z-10 flex flex-col items-center justify-center min-h-screen px-5 py-12 gap-8">

        {/* logos */}
        <div className="flex items-center justify-center gap-4">
          <Image src="/Hellmanns-Logo.png" alt="Hellmann's" width={48} height={48}
            className="object-contain drop-shadow-[0_0_12px_rgba(255,210,0,0.3)]" />
          <span className="font-display text-[#FFD200] text-3xl leading-none">×</span>
          <Image src="/National-Basketball-Association-Logo.png" alt="NBA" width={38} height={48} className="object-contain" />
        </div>

        {/* título */}
        <div className="text-center space-y-0">
          <p className="text-white/25 font-body text-[9px] tracking-[0.45em] uppercase mb-3">NBA HOUSE BRASIL</p>
          <h1 className="font-display text-[2.6rem] leading-[0.85] tracking-wider text-[#FFD200] drop-shadow-[0_0_40px_rgba(255,210,0,0.35)]">
            BASKET AIR CHALLENGE
          </h1>
          <h1 className="font-display text-[2.6rem] leading-[0.85] tracking-wider text-white">
            HELLMANNS
          </h1>
        </div>

        {/* divisor */}
        <div className="flex items-center gap-3 w-full max-w-xs">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#FFD200]/40" />
          <div className="h-1.5 w-10 bg-[#FFD200] rounded-full shadow-[0_0_12px_rgba(255,210,0,0.5)]" />
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#FFD200]/40" />
        </div>

        {/* badges com nomes dos participantes */}
        {session.participants.length > 0 && (
          <div className="flex flex-wrap justify-center gap-2">
            {session.participants.map((name, i) => (
              <span key={i}
                className="inline-flex items-center gap-2 bg-[#FFD200]/10 border border-[#FFD200]/25
                           text-[#FFD200] font-display tracking-wider text-base px-4 py-1.5 rounded-full">
                <span className="w-4 h-4 rounded-full bg-[#FFD200]/20 flex items-center justify-center text-[8px] text-[#FFD200]/70 font-display leading-none">
                  {i + 1}
                </span>
                {name.toUpperCase()}
              </span>
            ))}
          </div>
        )}

        {/* QR para face scan */}
        <div className="flex flex-col items-center gap-5 w-full max-w-xs p-6 rounded-3xl bg-white/[0.04] border border-white/10">
          <div className="text-center space-y-1">
            <p className="font-display text-[#FFD200] text-xl tracking-wider leading-none">
              ENCONTRE SEU VÍDEO
            </p>
            <p className="text-white/35 text-xs font-body max-w-[200px] mx-auto leading-snug">
              Escaneie com a câmera frontal e encontre seu vídeo pelo rosto
            </p>
          </div>

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/qrcode-meu-video.svg"
            alt="QR Code para encontrar seu vídeo"
            className="w-52 h-52 bg-white rounded-2xl p-3 shadow-[0_0_40px_rgba(255,210,0,0.15)]"
          />

          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
              session.indexing_status === "indexed"
                ? "bg-green-400"
                : "bg-[#FFD200] animate-pulse"
            }`} />
            <span className="text-white/30 text-[10px] font-body uppercase tracking-widest">
              {session.indexing_status === "indexed" ? "pronto para escanear" : "processando vídeos..."}
            </span>
          </div>
        </div>

        {/* botão nova sessão */}
        <a
          href="/operador"
          className="inline-flex items-center justify-center rounded-2xl bg-[#FFD200] px-10 py-4
                     font-display text-2xl tracking-[0.15em] text-[#0A0A0A]
                     shadow-[0_0_35px_rgba(255,210,0,0.25)] hover:bg-[#ffe033] active:scale-95 transition-all duration-150"
        >
          NOVA SESSÃO
        </a>

        {/* hashtags */}
        <div className="text-center pt-4">
          <p className="font-display text-[#FFD200] text-xl tracking-wider">#BasketAirChallenge</p>
          <p className="font-display text-white/30 text-base tracking-wider">#HellmannsNBA</p>
        </div>
      </main>
    </div>
  );
}
