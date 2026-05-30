import Image from "next/image";
import { getSessions, SessionSummary, GalleryVideo } from "@/lib/api";

export const dynamic = "force-dynamic";

interface VideoEntry {
  session: SessionSummary;
  video: GalleryVideo;
}

interface DayGroup {
  label: string;
  dateKey: string;
  entries: VideoEntry[];
}

function groupByDay(sessions: SessionSummary[]): DayGroup[] {
  const map = new Map<string, DayGroup>();

  for (const session of sessions) {
    const d = new Date(session.created_at);
    const dateKey = d.toISOString().split("T")[0]; // YYYY-MM-DD (UTC)
    const label = d.toLocaleDateString("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      timeZone: "America/Sao_Paulo",
    });

    if (!map.has(dateKey)) map.set(dateKey, { label, dateKey, entries: [] });

    for (const video of session.videos) {
      map.get(dateKey)!.entries.push({ session, video });
    }
  }

  // mais recente primeiro
  return Array.from(map.values()).sort((a, b) => b.dateKey.localeCompare(a.dateKey));
}

export default async function GaleriaIndexPage() {
  let sessions: SessionSummary[] = [];
  try {
    sessions = await getSessions();
  } catch {
    // mostra lista vazia em caso de erro
  }

  const days = groupByDay(sessions);
  const totalVideos = sessions.reduce((acc, s) => acc + s.videos.length, 0);

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
          <h1 className="font-display text-[3.6rem] leading-[0.85] tracking-wider text-[#FFD200] drop-shadow-[0_0_40px_rgba(255,210,0,0.35)]">BAZUCA</h1>
          <h1 className="font-display text-[3.6rem] leading-[0.85] tracking-wider text-white">DE BOLINHAS</h1>
        </div>

        <p className="text-white/40 text-sm mb-6">
          {days.length} dia(s) · {totalVideos} vídeo(s)
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

      {/* ── DIAS ── */}
      <main className="relative z-10 px-4 pb-12 max-w-[1500px] mx-auto space-y-14">
        {sessions.length === 0 && (
          <div className="text-center py-20">
            <p className="text-white/30 font-body text-sm">Nenhuma sessão finalizada ainda.</p>
          </div>
        )}

        {days.map((day) => (
          <section key={day.dateKey} id={`dia-${day.dateKey}`}>

            {/* cabeçalho do dia */}
            <div className="flex items-center gap-4 mb-6">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#FFD200] opacity-40" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-[#FFD200]" />
                </span>
                <h2 className="font-display text-[#FFD200] tracking-[0.2em] text-2xl capitalize">
                  {day.label}
                </h2>
              </div>
              <span className="text-white/25 text-sm">{day.entries.length} vídeo(s)</span>
              <div className="h-px flex-1 bg-white/10" />
            </div>

            {/* grid de vídeos do dia */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
              {day.entries.map(({ session, video }) => {
                const time = new Date(session.created_at).toLocaleTimeString("pt-BR", {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: "America/Sao_Paulo",
                });

                return (
                  <article
                    key={`${session.session_id}-${video.cabine_id}`}
                    className="rounded-3xl overflow-hidden bg-white/[0.04] border border-white/10 shadow-[0_12px_64px_rgba(0,0,0,0.7)]"
                  >
                    {/* header do card */}
                    <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 bg-gradient-to-r from-[#003B7A]/40 to-transparent">
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#E8003D]" />
                        <span className="text-white/50 text-xs font-body tracking-widest uppercase">
                          Cabine {video.cabine_id}
                        </span>
                      </div>
                      <span className="text-white/30 text-xs font-body">{time}</span>
                    </div>

                    {/* vídeo 9:16 */}
                    <div className="relative w-full" style={{ paddingBottom: "177.78%" }}>
                      <video
                        src={video.video_url}
                        controls
                        playsInline
                        preload="metadata"
                        className="absolute inset-0 w-full h-full object-contain bg-black"
                      />
                    </div>

                    {/* download */}
                    <a
                      href={video.video_url}
                      download={`bazuca-${session.session_id}-cabine${video.cabine_id}.mp4`}
                      className="flex items-center justify-center gap-3 w-full bg-[#FFD200] text-[#0A0A0A]
                                 font-display text-[1.6rem] tracking-[0.15em] py-5
                                 hover:bg-[#ffe033] active:scale-[0.98] transition-all duration-150 uppercase"
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
            </div>
          </section>
        ))}
      </main>

      <footer className="relative z-10 pb-10 px-5 text-center">
        <div className="flex items-center gap-3 mb-5">
          <div className="h-px flex-1 bg-white/10" />
          <div className="h-1 w-6 bg-[#FFD200]/40 rounded-full" />
          <div className="h-px flex-1 bg-white/10" />
        </div>
        <p className="font-display text-[#FFD200] text-2xl tracking-wider">#BazucadeBolinhas</p>
        <p className="font-display text-white/30 text-lg tracking-wider">#HellmannsNBA</p>
      </footer>
    </div>
  );
}
