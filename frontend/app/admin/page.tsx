"use client";
import { useEffect, useState, useCallback } from "react";
import Image from "next/image";

interface HourBucket {
  hour: string;
  count: number;
}

interface DayBucket {
  day: string;
  videos: number;
  sessions: number;
}

interface RecentSession {
  session_id: string;
  operator_name: string;
  created_at: string | null;
  status: string;
  video_count: number;
  participant_count: number;
}

interface AdminStats {
  sessions_today: number;
  videos_today: number;
  total_sessions: number;
  total_videos: number;
  recording_now: number;
  sessions_per_hour: HourBucket[];
  videos_per_day: DayBucket[];
  recent_sessions: RecentSession[];
  updated_at: string;
}

const REFRESH_S = 15;

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(REFRESH_S);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/admin/stats", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStats(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setLoading(false);
      setCountdown(REFRESH_S);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const iv = setInterval(fetchStats, REFRESH_S * 1000);
    return () => clearInterval(iv);
  }, [fetchStats]);

  // Countdown between refreshes
  useEffect(() => {
    const t = setInterval(
      () => setCountdown((c) => (c <= 1 ? REFRESH_S : c - 1)),
      1000,
    );
    return () => clearInterval(t);
  }, []);

  const maxH = stats
    ? Math.max(...stats.sessions_per_hour.map((h) => h.count), 1)
    : 1;

  const maxV = stats
    ? Math.max(...stats.videos_per_day.map((d) => d.videos), 1)
    : 1;

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white font-body">
      {/* Background */}
      <div className="fixed inset-0 pointer-events-none select-none" aria-hidden>
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 50% at 50% 0%, rgba(0,59,122,0.30) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage:
              "repeating-linear-gradient(-45deg, #FFD200 0, #FFD200 1px, transparent 0, transparent 40px)",
            backgroundSize: "56px 56px",
          }}
        />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-20 flex items-center justify-between px-5 py-3 border-b border-white/10 bg-black/70 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <Image
            src="/Hellmanns-Logo.png"
            alt="Hellmann's"
            width={28}
            height={28}
            className="object-contain flex-shrink-0"
          />
          <span className="font-display text-[#FFD200] text-lg leading-none tracking-wider">
            ×
          </span>
          <Image
            src="/National-Basketball-Association-Logo.png"
            alt="NBA"
            width={20}
            height={28}
            className="object-contain flex-shrink-0"
          />
          <span className="font-display text-white/40 text-sm tracking-[0.25em] ml-2 hidden sm:block">
            DASHBOARD
          </span>
        </div>

        <div className="flex items-center gap-3">
          {stats && stats.recording_now > 0 && (
            <span className="flex items-center gap-1.5 bg-[#E8003D]/15 border border-[#E8003D]/30 text-[#E8003D] font-display text-[10px] tracking-[0.2em] px-3 py-1 rounded-full">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E8003D] opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#E8003D]" />
              </span>
              GRAVANDO
            </span>
          )}
          <span className="text-white/25 text-xs font-body tabular-nums">
            {loading ? "..." : error ? "ERRO" : `↻ ${countdown}s`}
          </span>
        </div>
      </header>

      <main className="relative z-10 max-w-5xl mx-auto px-4 py-8 space-y-6">
        {/* Error banner */}
        {error && (
          <div className="bg-[#E8003D]/10 border border-[#E8003D]/30 text-[#E8003D] text-sm px-4 py-3 rounded-xl">
            Erro ao carregar: {error}
          </div>
        )}

        {/* ── Stat cards ── */}
        <div className="grid grid-cols-2 gap-4">
          <StatCard
            label="Sessões hoje"
            value={stats?.sessions_today ?? "—"}
            sub={`${stats?.total_sessions ?? 0} no total`}
            accent="#FFD200"
          />
          <StatCard
            label="Vídeos hoje"
            value={stats?.videos_today ?? "—"}
            sub={`${stats?.total_videos ?? 0} no total`}
            accent="#FFD200"
          />
        </div>

        {/* ── Sessions per hour chart ── */}
        <section className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
          <h2 className="font-display text-[#FFD200] tracking-[0.2em] text-xs uppercase mb-5">
            Sessões por hora · últimas 24h · horário SP
          </h2>

          {stats ? (
            <div className="flex items-end gap-px h-28">
              {stats.sessions_per_hour.map(({ hour, count }, idx) => (
                <div
                  key={hour}
                  className="flex-1 flex flex-col items-center gap-1 min-w-0"
                >
                  <span className="text-[8px] text-white/50 tabular-nums h-3 leading-3">
                    {count > 0 ? count : ""}
                  </span>
                  <div
                    className="w-full rounded-t-sm transition-all duration-500"
                    style={{
                      height:
                        count > 0
                          ? `${Math.max(4, (count / maxH) * 72)}px`
                          : "2px",
                      backgroundColor:
                        count > 0
                          ? "rgba(255,210,0,0.70)"
                          : "rgba(255,255,255,0.06)",
                    }}
                  />
                  <span className="text-[8px] text-white/20 truncate w-full text-center leading-3">
                    {idx % 4 === 0 ? hour : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-28 flex items-center justify-center">
              <div className="w-6 h-6 rounded-full border-2 border-white/10 border-t-white/30 animate-spin" />
            </div>
          )}
        </section>

        {/* ── Videos per day chart ── */}
        <section className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
          <h2 className="font-display text-[#FFD200] tracking-[0.2em] text-xs uppercase mb-5">
            Vídeos por dia · últimos 7 dias · horário SP
          </h2>

          {stats ? (
            <div className="flex items-end gap-2 h-36">
              {stats.videos_per_day.map(({ day, videos, sessions }) => (
                <div
                  key={day}
                  className="flex-1 flex flex-col items-center gap-1 min-w-0"
                >
                  <span className="text-[9px] text-white/50 tabular-nums h-3 leading-3">
                    {videos > 0 ? videos : ""}
                  </span>
                  <div className="w-full flex flex-col-reverse gap-px">
                    <div
                      className="w-full rounded-t-sm transition-all duration-500"
                      title={`${videos} vídeo${videos !== 1 ? "s" : ""} · ${sessions} sessão`}
                      style={{
                        height:
                          videos > 0
                            ? `${Math.max(4, (videos / maxV) * 88)}px`
                            : "2px",
                        backgroundColor:
                          videos > 0
                            ? "rgba(255,210,0,0.70)"
                            : "rgba(255,255,255,0.06)",
                      }}
                    />
                  </div>
                  <span className="text-[9px] text-white/30 truncate w-full text-center leading-3">
                    {day}
                  </span>
                  {sessions > 0 && (
                    <span className="text-[8px] text-white/20 leading-3">
                      {sessions}s
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="h-36 flex items-center justify-center">
              <div className="w-6 h-6 rounded-full border-2 border-white/10 border-t-white/30 animate-spin" />
            </div>
          )}
        </section>

        {/* ── Recent sessions table ── */}
        <section className="bg-white/[0.03] border border-white/10 rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/10">
            <h2 className="font-display text-[#FFD200] tracking-[0.2em] text-xs uppercase">
              Últimas sessões
            </h2>
          </div>

          {loading && !stats ? (
            <div className="px-5 py-8 text-center text-white/25 text-sm">
              Carregando...
            </div>
          ) : stats?.recent_sessions.length ? (
            <div className="divide-y divide-white/[0.05]">
              {stats.recent_sessions.map((s) => (
                <div
                  key={s.session_id}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition-colors"
                >
                  <span className="font-mono text-[11px] text-white/35 w-16 flex-shrink-0">
                    #{s.session_id}
                  </span>
                  <span className="text-sm text-white/65 flex-1 truncate min-w-0">
                    {s.operator_name}
                  </span>
                  <span className="text-[11px] text-white/35 flex-shrink-0 tabular-nums">
                    {s.created_at
                      ? new Date(s.created_at).toLocaleTimeString("pt-BR", {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: "America/Sao_Paulo",
                        })
                      : "—"}
                  </span>
                  <span className="text-[11px] text-white/40 flex-shrink-0">
                    {s.video_count} vídeo{s.video_count !== 1 ? "s" : ""}
                  </span>
                  <StatusBadge status={s.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="px-5 py-8 text-center text-white/25 text-sm">
              Nenhuma sessão ainda.
            </div>
          )}
        </section>

        {/* Footer */}
        {stats && (
          <p className="text-center text-white/15 text-xs font-body pb-4">
            Atualizado às{" "}
            {new Date(stats.updated_at).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              timeZone: "America/Sao_Paulo",
            })}{" "}
            (SP) · próxima atualização em {countdown}s
          </p>
        )}
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number | string;
  sub: string;
  accent: string;
}) {
  return (
    <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5 space-y-1">
      <p className="text-white/35 text-[10px] uppercase tracking-widest font-body">
        {label}
      </p>
      <p
        className="font-display text-[2.4rem] leading-none"
        style={{ color: accent }}
      >
        {value}
      </p>
      <p className="text-white/30 text-xs font-body">{sub}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ready")
    return (
      <span className="text-[10px] bg-green-500/15 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full font-body flex-shrink-0">
        ok
      </span>
    );
  if (status === "recording")
    return (
      <span className="text-[10px] bg-[#E8003D]/15 text-[#E8003D] border border-[#E8003D]/25 px-2 py-0.5 rounded-full font-body flex-shrink-0">
        gravando
      </span>
    );
  return (
    <span className="text-[10px] bg-red-500/15 text-red-400 border border-red-500/20 px-2 py-0.5 rounded-full font-body flex-shrink-0">
      erro
    </span>
  );
}
