"use client";
import { useEffect, useRef, useState } from "react";
import { SessionSummary, GalleryVideo } from "@/lib/api";
import { VideoCard } from "./VideoCard";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001";

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
    const dateKey = d.toISOString().split("T")[0];
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
  return Array.from(map.values()).sort((a, b) => b.dateKey.localeCompare(a.dateKey));
}

interface GalleryClientProps {
  initialSessions: SessionSummary[];
  initialHasMore: boolean;
}

export function GalleryClient({ initialSessions, initialHasMore }: GalleryClientProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>(initialSessions);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hasMore) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !loading) {
          loadMore();
        }
      },
      { rootMargin: "400px" }
    );
    const el = sentinelRef.current;
    if (el) observer.observe(el);
    return () => { if (el) observer.unobserve(el); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, loading, page]);

  async function loadMore() {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const nextPage = page + 1;
      const res = await fetch(`${API_BASE}/sessions?page=${nextPage}&limit=20`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setSessions(prev => [...prev, ...(data.sessions || [])]);
      setHasMore(data.has_more ?? false);
      setPage(nextPage);
    } catch {
      // silently fail — user can scroll again to retry
    } finally {
      setLoading(false);
    }
  }

  const days = groupByDay(sessions);

  if (sessions.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-white/30 font-body text-sm">Nenhuma sessão finalizada ainda.</p>
      </div>
    );
  }

  return (
    <main className="relative z-10 px-4 pb-12 max-w-[1500px] mx-auto space-y-14">
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

          {/* grid */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {day.entries.map(({ session, video }) => {
              const time = new Date(session.created_at).toLocaleTimeString("pt-BR", {
                hour: "2-digit",
                minute: "2-digit",
                timeZone: "America/Sao_Paulo",
              });
              return (
                <VideoCard
                  key={`${session.session_id}-${video.cabine_id}`}
                  src={video.video_url}
                  cabineId={video.cabine_id}
                  time={time}
                  sessionId={session.session_id}
                  qrUrl={video.qr_url}
                />
              );
            })}
          </div>
        </section>
      ))}

      {/* sentinel para infinite scroll */}
      <div ref={sentinelRef} className="h-4" />

      {loading && (
        <div className="flex justify-center py-6">
          <div className="w-8 h-8 rounded-full border-2 border-white/10 border-t-white/30 animate-spin" />
        </div>
      )}

      {!hasMore && sessions.length > 0 && (
        <p className="text-center text-white/15 font-body text-xs tracking-widest pb-4">· fim ·</p>
      )}
    </main>
  );
}
