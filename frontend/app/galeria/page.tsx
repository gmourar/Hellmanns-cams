import Image from "next/image";
import { getSessions, SessionSummary } from "@/lib/api";
import { GalleryClient } from "./GalleryClient";

export const dynamic = "force-dynamic";

function groupDaysForNav(sessions: SessionSummary[]) {
  const map = new Map<string, string>();
  for (const session of sessions) {
    const d = new Date(session.created_at);
    const dateKey = d.toISOString().split("T")[0];
    if (!map.has(dateKey)) {
      map.set(dateKey, d.toLocaleDateString("pt-BR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        timeZone: "America/Sao_Paulo",
      }));
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([dateKey, label]) => ({ dateKey, label }));
}

export default async function GaleriaIndexPage() {
  let initialSessions: SessionSummary[] = [];
  let initialHasMore = false;
  try {
    const data = await getSessions(1, 20);
    initialSessions = data.sessions;
    initialHasMore = data.has_more;
  } catch {
    // mostra lista vazia em caso de erro
  }

  const days = groupDaysForNav(initialSessions);
  const totalVideos = initialSessions.reduce((acc, s) => acc + s.videos.length, 0);

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

      {/* ── HERO ── */}
      <header className="relative z-10 px-5 pt-10 pb-8 text-center">
        <div className="flex items-center justify-center gap-4 mb-7">
          <Image src="/Hellmanns-Logo.png" alt="Hellmann's" width={44} height={44}
            className="object-contain drop-shadow-[0_0_12px_rgba(255,210,0,0.3)]" />
          <span className="font-display text-[#FFD200] text-3xl leading-none">×</span>
          <Image src="/National-Basketball-Association-Logo.png" alt="NBA" width={36} height={44} className="object-contain" />
        </div>

        <p className="text-white/25 font-body text-[9px] tracking-[0.45em] uppercase mb-2">NBA HOUSE BRASIL</p>
        <div className="space-y-0 mb-4">
          <h1 className="font-display text-[2.8rem] leading-[0.85] tracking-wider text-[#FFD200] drop-shadow-[0_0_40px_rgba(255,210,0,0.35)]">
            BASKET AIR CHALLENGE
          </h1>
          <h1 className="font-display text-[2.8rem] leading-[0.85] tracking-wider text-white">
            HELLMANNS
          </h1>
        </div>

        <p className="text-white/40 text-sm mb-6">
          {days.length} dia(s) · {totalVideos}{initialHasMore ? "+" : ""} vídeo(s)
        </p>

        {/* Navegação por dia */}
        {days.length > 1 && (
          <div className="flex justify-center gap-3 flex-wrap mb-2">
            {days.map((day) => (
              <a key={day.dateKey} href={`#dia-${day.dateKey}`}
                className="font-display text-sm tracking-widest bg-[#FFD200]/10 border border-[#FFD200]/30 text-[#FFD200] px-5 py-2 rounded-full hover:bg-[#FFD200]/20 transition-colors capitalize">
                {day.label}
              </a>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3 mt-6 mb-5 px-2">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#FFD200]/40" />
          <div className="h-1.5 w-10 bg-[#FFD200] rounded-full shadow-[0_0_12px_rgba(255,210,0,0.5)]" />
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#FFD200]/40" />
        </div>
      </header>

      {/* ── GALLERY (client component handles lazy load + infinite scroll) ── */}
      <GalleryClient initialSessions={initialSessions} initialHasMore={initialHasMore} />

      <footer className="relative z-10 pb-10 px-5 text-center">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-px flex-1 bg-white/10" />
          <div className="h-1 w-6 bg-[#FFD200]/40 rounded-full" />
          <div className="h-px flex-1 bg-white/10" />
        </div>
        <p className="font-display text-[#FFD200] text-2xl tracking-wider">#BasketAirChallenge</p>
        <p className="font-display text-white/30 text-lg tracking-wider">#HellmannsNBA</p>
      </footer>
    </div>
  );
}
