"use client";

import { useState } from "react";
import Image from "next/image";
import { startSession, getGallery } from "@/lib/api";

type Phase = "idle" | "recording" | "processing" | "error";

const RECORD_SECONDS = 5;

// ─── inline SVG camera ────────────────────────────────────────────────────────
function CameraIcon({ active, size = "md" }: { active?: boolean; size?: "sm" | "md" }) {
  const sz = size === "sm" ? "w-5 h-5" : "w-7 h-7";
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={active ? 2.5 : 1.5}
      className={`${sz} transition-colors duration-300 ${active ? "text-[#E8003D]" : "text-white/40"}`}
    >
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M15.75 10.5l4.72-2.36A1 1 0 0122 9.07v5.86a1 1 0 01-1.53.89L15.75 13.5m-9 1.5h6a2.25 2.25 0 002.25-2.25v-4.5A2.25 2.25 0 0012.75 6h-6A2.25 2.25 0 004.5 8.25v4.5A2.25 2.25 0 006.75 15z" />
    </svg>
  );
}

// ─── header com logos ─────────────────────────────────────────────────────────
function BrandBar({ dot }: { dot: "online" | "recording" | "off" }) {
  const dotCls = dot === "recording" ? "bg-[#E8003D] animate-pulse" : dot === "online" ? "bg-green-400" : "bg-white/20";
  const dotLabel = dot === "recording" ? "Gravando" : dot === "online" ? "Online" : "Offline";
  return (
    <header className="relative z-20 flex items-center justify-between px-5 py-3 border-b border-white/10 bg-black/60 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <Image src="/Hellmanns-Logo.png" alt="Hellmann's" width={32} height={32} className="object-contain flex-shrink-0" />
        <span className="font-display text-[#FFD200] text-lg leading-none tracking-wider">×</span>
        <Image src="/National-Basketball-Association-Logo.png" alt="NBA" width={24} height={32} className="object-contain flex-shrink-0" />
        <span className="font-display text-white/30 text-xs tracking-[0.25em] hidden sm:block">HOUSE BRASIL</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${dotCls}`} />
        <span className="text-[10px] uppercase tracking-widest text-white/40 font-body">{dotLabel}</span>
      </div>
    </header>
  );
}

// ─── fundo com textura ────────────────────────────────────────────────────────
function Background() {
  return (
    <div className="absolute inset-0 pointer-events-none select-none overflow-hidden" aria-hidden>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/bg-texture.jpg" alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-[0.12]"
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
      />
      <div className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse 80% 60% at 50% 40%, rgba(0,59,122,0.35) 0%, transparent 70%)" }}
      />
      <div className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: "repeating-linear-gradient(-45deg, #FFD200 0, #FFD200 1px, transparent 0, transparent 40px)",
          backgroundSize: "56px 56px",
        }}
      />
      <div className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(0,0,0,0.7) 100%)" }}
      />
    </div>
  );
}

// ─── bola decorativa ──────────────────────────────────────────────────────────
function Ball({ className }: { className?: string }) {
  return (
    <div className={className} aria-hidden>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/image-removebg-preview.png" alt=""
        className="w-full h-full object-contain select-none pointer-events-none"
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
      />
    </div>
  );
}

// ─── componente principal ─────────────────────────────────────────────────────
export default function OperadorPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [secondsLeft, setSecondsLeft] = useState(RECORD_SECONDS);
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    try {
      setError(null);
      setPhase("recording");
      setSecondsLeft(RECORD_SECONDS);
      const resp = await startSession({ operator_name: "Promotor da ativação", participants: [] });
      const iv = setInterval(() => {
        setSecondsLeft((s) => {
          if (s <= 1) { clearInterval(iv); setPhase("processing"); pollForVideos(resp.session_id); return 0; }
          return s - 1;
        });
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "erro desconhecido");
      setPhase("error");
    }
  }

  async function pollForVideos(id: string) {
    for (let i = 0; i < 180; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const gallery = await getGallery(id);
        if (gallery.status === "ready" && gallery.videos.length > 0) {
          window.location.assign(`/galeria/${id}`);
          return;
        }
      } catch { /* aguarda */ }
    }
    setError("Vídeos demoraram demais — verifique o agente");
    setPhase("error");
  }

  function reset() {
    setPhase("idle");
    setError(null);
  }

  const progress = ((RECORD_SECONDS - secondsLeft) / RECORD_SECONDS) * 100;
  const dot: "online" | "recording" | "off" = phase === "recording" ? "recording" : phase === "error" ? "off" : "online";

  return (
    <div className="relative min-h-screen flex flex-col bg-[#0A0A0A] overflow-hidden font-body">
      <Background />
      <BrandBar dot={dot} />

      {/* ══════════════════════════════════════════════════════════ IDLE */}
      {phase === "idle" && (
        <main className="relative z-10 flex-1 flex flex-col items-center justify-between px-6 pt-6 pb-10">
          {/* bola decorativa — canto superior direito */}
          <Ball className="absolute top-0 right-[-10%] w-64 h-64 opacity-[0.18] pointer-events-none" />
          {/* bola espelhada — canto inferior esquerdo */}
          <Ball className="absolute bottom-24 left-[-15%] w-48 h-48 opacity-[0.08] pointer-events-none" />

          {/* conteúdo central */}
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-5 w-full max-w-sm">
            {/* badge topo */}
            <span className="inline-flex items-center gap-2 bg-[#FFD200]/10 border border-[#FFD200]/25 text-[#FFD200] font-display text-xs tracking-[0.3em] px-4 py-1.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              PAINEL DO OPERADOR
            </span>

            {/* título principal */}
            <div className="space-y-0">
              <h1 className="font-display text-[5.5rem] leading-[0.85] tracking-wider text-white drop-shadow-[0_2px_24px_rgba(0,0,0,0.8)]">
                BAZUCA
              </h1>
              <h1 className="font-display text-[5.5rem] leading-[0.85] tracking-wider text-[#FFD200] drop-shadow-[0_0_40px_rgba(255,210,0,0.4)]">
                DE
              </h1>
              <h1 className="font-display text-[5.5rem] leading-[0.85] tracking-wider text-white drop-shadow-[0_2px_24px_rgba(0,0,0,0.8)]">
                BOLINHAS
              </h1>
            </div>

            {/* divisor */}
            <div className="flex items-center gap-3 w-full max-w-[200px]">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#FFD200]/40" />
              <div className="h-1 w-8 bg-[#FFD200] rounded-full" />
              <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#FFD200]/40" />
            </div>

            <p className="text-white/30 text-xs tracking-[0.3em] uppercase font-body">
              3 CÂMERAS · {RECORD_SECONDS}S · SLOW-MOTION
            </p>

            {/* indicadores de câmera */}
            <div className="flex items-center justify-center gap-4 pt-1">
              {[1, 2, 3].map((n) => (
                <div key={n} className="flex flex-col items-center gap-1.5">
                  <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-sm">
                    <CameraIcon />
                  </div>
                  <span className="text-[9px] text-white/25 tracking-widest font-body uppercase">CAM {n}</span>
                </div>
              ))}
            </div>
          </div>

          {/* botão INICIAR — zona do polegar */}
          <div className="w-full max-w-sm space-y-2">
            <button
              onClick={handleStart}
              className="w-full bg-[#FFD200] text-[#0A0A0A] font-display text-[2.4rem] tracking-[0.15em] py-6 rounded-3xl
                         shadow-[0_0_60px_rgba(255,210,0,0.4),0_4px_20px_rgba(0,0,0,0.5)]
                         hover:shadow-[0_0_90px_rgba(255,210,0,0.6),0_4px_20px_rgba(0,0,0,0.5)]
                         hover:bg-[#ffe033]
                         active:scale-95 transition-all duration-150 uppercase"
            >
              INICIAR
            </button>
            <p className="text-center text-white/15 text-[10px] tracking-[0.35em] uppercase font-body">
              toque para começar
            </p>
          </div>
        </main>
      )}

      {/* ══════════════════════════════════════════════════════════ RECORDING */}
      {phase === "recording" && (
        <main className="relative z-10 flex-1 flex flex-col items-center justify-between px-6 py-8 animate-pulse_red">
          {/* tinta vermelha de fundo */}
          <div className="absolute inset-0 bg-[#E8003D]/12 pointer-events-none" aria-hidden />
          <div className="absolute inset-0 pointer-events-none" aria-hidden
            style={{ background: "radial-gradient(ellipse 70% 50% at 50% 50%, rgba(232,0,61,0.15) 0%, transparent 70%)" }}
          />

          {/* topo */}
          <div className="flex flex-col items-center gap-3 pt-2 w-full">
            <div className="flex items-center gap-2.5 bg-[#E8003D]/20 border border-[#E8003D]/40 px-5 py-2 rounded-full">
              <span className="w-3 h-3 rounded-full bg-[#E8003D] animate-pulse flex-shrink-0" />
              <span className="font-display text-[#E8003D] text-2xl tracking-[0.35em] leading-none">
                GRAVANDO AO VIVO
              </span>
            </div>

            {/* número gigante */}
            <div
              className="font-display text-[12rem] leading-none text-[#FFD200] tabular-nums
                         drop-shadow-[0_0_80px_rgba(255,210,0,0.6)]"
              style={{ textShadow: "0 0 120px rgba(255,210,0,0.4), 0 4px 32px rgba(0,0,0,0.8)" }}
              aria-live="assertive"
              aria-label={`${secondsLeft} segundos restantes`}
            >
              {secondsLeft}
            </div>

            <p className="text-white/30 font-body text-xs tracking-[0.35em] uppercase">
              SEGUNDOS RESTANTES
            </p>
          </div>

          {/* barra e câmeras */}
          <div className="w-full max-w-sm space-y-5">
            <div className="relative w-full bg-white/10 rounded-full h-2.5 overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-[#FFD200] rounded-full transition-all duration-1000 ease-linear
                              shadow-[0_0_12px_rgba(255,210,0,0.6)]"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="flex items-center justify-center gap-5">
              {[1, 2, 3].map((n) => (
                <div key={n} className="flex flex-col items-center gap-1.5">
                  <div className="relative w-14 h-14 rounded-2xl bg-[#E8003D]/15 border border-[#E8003D]/50 flex items-center justify-center">
                    <CameraIcon active />
                    {/* ping indicator */}
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#E8003D] animate-ping opacity-75" />
                  </div>
                  <span className="text-[9px] text-[#E8003D]/70 uppercase tracking-widest font-body">REC {n}</span>
                </div>
              ))}
            </div>

            <p className="text-center text-white/25 font-body text-xs tracking-widest uppercase">
              3 câmeras · slow-motion
            </p>
          </div>
        </main>
      )}

      {/* ══════════════════════════════════════════════════════════ PROCESSING */}
      {phase === "processing" && (
        <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-8 gap-10">
          {/* bola girando */}
          <div className="relative w-28 h-28">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/image-removebg-preview.png" alt=""
              className="w-28 h-28 object-contain animate-spin_slow"
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
            />
            {/* anel externo */}
            <div className="absolute inset-[-8px] rounded-full border-2 border-dashed border-[#FFD200]/20 animate-spin"
              style={{ animationDuration: "8s" }} />
          </div>

          <div className="text-center space-y-1">
            <h2 className="font-display text-[3rem] tracking-wider text-white leading-none">
              EDITANDO<span className="text-[#FFD200]">...</span>
            </h2>
            <p className="text-white/35 font-body text-sm">aguenta um segundo, parceiro</p>
          </div>

          <div className="w-full max-w-xs space-y-3">
            {["Preparando o vídeo", "Aplicando velocidade 0.60x", "Subindo para a cloud", "Indexando rostos", "Pronto!"].map((step, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-5 h-5 rounded-full border border-[#FFD200]/30 bg-[#FFD200]/10 flex items-center justify-center flex-shrink-0">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#FFD200]/60" />
                </div>
                <span className="text-white/45 font-body text-sm">{step}</span>
              </div>
            ))}
          </div>
        </main>
      )}

      {/* ══════════════════════════════════════════════════════════ ERROR */}
      {phase === "error" && (
        <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-8 gap-7 text-center">
          <div className="relative">
            <div className="w-24 h-24 rounded-3xl bg-[#E8003D]/10 border border-[#E8003D]/30 flex items-center justify-center">
              <span className="font-display text-[4rem] text-[#E8003D] leading-none">!</span>
            </div>
            <div className="absolute inset-0 rounded-3xl border border-[#E8003D]/15 scale-110 animate-pulse" />
          </div>

          <div className="space-y-2 max-w-xs">
            <h2 className="font-display text-[2.4rem] tracking-wider text-[#FFD200] leading-none">
              ALGO DEU ERRADO
            </h2>
            <p className="text-white/50 font-body text-sm leading-relaxed">{error ?? "Erro desconhecido"}</p>
          </div>

          <button onClick={reset}
            className="bg-white text-[#0A0A0A] font-display text-[1.8rem] tracking-wider px-12 py-5 rounded-2xl
                       active:scale-95 transition-all duration-150 uppercase
                       shadow-[0_4px_24px_rgba(0,0,0,0.4)]"
          >
            TENTAR NOVAMENTE
          </button>
        </main>
      )}
    </div>
  );
}
