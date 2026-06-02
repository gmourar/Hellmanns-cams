"use client";
import { useEffect, useRef, useState } from "react";
import { QrDropdown } from "./QrDropdown";

interface VideoCardProps {
  src: string;
  cabineId: number;
  time: string;
  sessionId: string;
  qrUrl?: string;
}

export function VideoCard({ src, cabineId, time, sessionId, qrUrl }: VideoCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" }
    );
    const el = containerRef.current;
    if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <article className="rounded-3xl overflow-hidden bg-white/[0.04] border border-white/10 shadow-[0_12px_64px_rgba(0,0,0,0.7)]">
      {/* header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 bg-gradient-to-r from-[#003B7A]/40 to-transparent">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[#E8003D]" />
          <span className="text-white/50 text-xs font-body tracking-widest uppercase">
            Cabine {cabineId}
          </span>
        </div>
        <span className="text-white/30 text-xs font-body">{time}</span>
      </div>

      {/* video 9:16 */}
      <div ref={containerRef} className="relative w-full" style={{ paddingBottom: "177.78%" }}>
        {visible ? (
          <video
            src={src}
            controls
            playsInline
            preload="metadata"
            className="absolute inset-0 w-full h-full object-contain bg-black"
          />
        ) : (
          <div className="absolute inset-0 bg-[#111] flex items-center justify-center">
            <div className="w-8 h-8 rounded-full border-2 border-white/10 border-t-white/30 animate-spin" />
          </div>
        )}
      </div>

      {/* QR dropdown */}
      {qrUrl && <QrDropdown qrUrl={qrUrl} cabineId={cabineId} />}

      {/* download */}
      <a
        href={src}
        download={`basket-air-challenge-${sessionId}-cabine${cabineId}.mp4`}
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
}
