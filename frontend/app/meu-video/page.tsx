"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { buscarVideo, BuscarVideoResponse } from "@/lib/api";

type Phase = "camera" | "capturing" | "searching" | "result" | "error";

export default function MeuVideoPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [phase, setPhase] = useState<Phase>("camera");
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<BuscarVideoResponse[]>([]);
  const [camError, setCamError] = useState<string | null>(null);

  useEffect(() => {
    let stream: MediaStream | null = null;
    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch {
        setCamError("Não foi possível acessar a câmera. Verifique as permissões.");
      }
    }
    startCamera();
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function handleCapture() {
    if (!videoRef.current || !canvasRef.current) return;
    setPhase("capturing");

    // Flash de 200ms
    await new Promise((r) => setTimeout(r, 200));

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Espelha a imagem (câmera frontal é espelhada no preview, mas para Rekognition precisa não-espelhada)
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0);

    // Converte para base64 JPEG (remove prefixo data:image/jpeg;base64,)
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    const base64 = dataUrl.split(",")[1];

    setPhase("searching");

    try {
      const data = await buscarVideo(base64);
      setResults(data);
      setPhase("result");
      // Para a câmera para economizar bateria
      (videoRef.current?.srcObject as MediaStream)?.getTracks().forEach((t) => t.stop());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
      setPhase("error");
    }
  }

  function resetar() {
    setPhase("camera");
    setError(null);
    setResults([]);
    // Reinicia câmera
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } }).then((stream) => {
      if (videoRef.current) videoRef.current.srcObject = stream;
    });
  }

  return (
    <div className="relative min-h-screen flex flex-col bg-[#0A0A0A] overflow-hidden font-body">
      {/* Background — mesmo padrão das outras páginas */}
      <div className="absolute inset-0 pointer-events-none select-none" aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/bg-texture.jpg" alt="" className="absolute inset-0 w-full h-full object-cover opacity-[0.12]"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
        <div className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse 80% 60% at 50% 40%, rgba(0,59,122,0.35) 0%, transparent 70%)" }} />
        <div className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: "repeating-linear-gradient(-45deg, #FFD200 0, #FFD200 1px, transparent 0, transparent 40px)", backgroundSize: "56px 56px" }} />
        <div className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(0,0,0,0.7) 100%)" }} />
      </div>

      {/* Header */}
      <header className="relative z-20 flex items-center justify-between px-5 py-3 border-b border-white/10 bg-black/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <Image src="/Hellmanns-Logo.png" alt="Hellmann's" width={32} height={32} className="object-contain flex-shrink-0" />
          <span className="font-display text-[#FFD200] text-lg leading-none tracking-wider">×</span>
          <Image src="/National-Basketball-Association-Logo.png" alt="NBA" width={24} height={32} className="object-contain flex-shrink-0" />
        </div>
        <span className="text-[10px] uppercase tracking-widest text-white/30 font-body">MEU VÍDEO</span>
      </header>

      <canvas ref={canvasRef} className="hidden" />

      <main className="relative z-10 flex-1 flex flex-col items-center justify-between px-5 pt-6 pb-10">

        {/* CAMERA */}
        {(phase === "camera" || phase === "capturing") && (
          <>
            <div className="text-center space-y-1 mb-4">
              <h1 className="font-display text-[2.8rem] leading-[0.9] tracking-wider text-white">
                ENCONTRE SEU <span className="text-[#FFD200]">VÍDEO</span>
              </h1>
              <p className="text-white/35 text-sm font-body">
                {camError ?? "Posicione seu rosto e tire uma foto"}
              </p>
            </div>

            {/* Preview da câmera */}
            <div className="relative w-full max-w-sm aspect-[3/4] rounded-3xl overflow-hidden border border-white/10 bg-black/40">
              {/* Vídeo espelhado para UX (selfie look) */}
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
                style={{ transform: "scaleX(-1)" }}
              />
              {/* Guia de rosto */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-48 h-56 rounded-full border-2 border-[#FFD200]/40 border-dashed" />
              </div>
              {/* Flash ao capturar */}
              {phase === "capturing" && (
                <div className="absolute inset-0 bg-white/80 animate-pulse" />
              )}
            </div>

            {!camError && (
              <button
                onClick={handleCapture}
                disabled={phase === "capturing"}
                className="mt-6 w-full max-w-sm bg-[#FFD200] text-[#0A0A0A] font-display text-[2rem] tracking-[0.15em] py-6 rounded-3xl
                           shadow-[0_0_60px_rgba(255,210,0,0.4)]
                           hover:bg-[#ffe033] active:scale-95 transition-all duration-150 uppercase
                           disabled:opacity-50 disabled:cursor-not-allowed"
              >
                TIRAR FOTO
              </button>
            )}
          </>
        )}

        {/* SEARCHING */}
        {phase === "searching" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-8">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/image-removebg-preview.png" alt="" className="w-24 h-24 object-contain animate-spin"
              style={{ animationDuration: "2s" }}
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
            <div className="text-center space-y-1">
              <h2 className="font-display text-[2.4rem] tracking-wider text-white leading-none">
                BUSCANDO<span className="text-[#FFD200]">...</span>
              </h2>
              <p className="text-white/35 font-body text-sm">Procurando seu vídeo</p>
            </div>
          </div>
        )}

        {/* RESULT */}
        {phase === "result" && results.length > 0 && (
          <div className="w-full max-w-sm space-y-5">
            <div className="text-center space-y-1">
              <span className="inline-flex items-center gap-2 bg-[#FFD200]/10 border border-[#FFD200]/25 text-[#FFD200] font-display text-xs tracking-[0.25em] px-4 py-1.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-[#FFD200]" />
                {results.length === 1 ? "VÍDEO ENCONTRADO" : `${results.length} VÍDEOS ENCONTRADOS`}
              </span>
              <h2 className="font-display text-[2.2rem] tracking-wider text-white leading-[0.95] pt-1">
                ESSE É O<br /><span className="text-[#FFD200]">SEU MOMENTO</span>
              </h2>
            </div>

            {results.map((result, i) => (
              <div key={`${result.session_id}-${result.cabine_id}`} className="space-y-3">
                {results.length > 1 && (
                  <p className="text-white/40 font-display text-sm tracking-widest text-center uppercase">
                    Cabine {result.cabine_id}
                  </p>
                )}
                {/* Player */}
                <div className="relative w-full rounded-3xl overflow-hidden border border-white/10 bg-black"
                  style={{ paddingBottom: "177.78%" }}>
                  <video
                    src={result.video_url}
                    controls
                    playsInline
                    autoPlay={i === 0}
                    className="absolute inset-0 w-full h-full object-contain"
                  />
                </div>
                {/* Download */}
                <a
                  href={result.video_url}
                  download={`bazuca-cabine${result.cabine_id}.mp4`}
                  className="flex items-center justify-center gap-3 w-full bg-[#FFD200] text-[#0A0A0A]
                             font-display text-[1.6rem] tracking-[0.15em] py-5 rounded-2xl
                             hover:bg-[#ffe033] active:scale-[0.98] transition-all duration-150 uppercase
                             shadow-[0_0_40px_rgba(255,210,0,0.3)]"
                >
                  BAIXAR VÍDEO {results.length > 1 ? result.cabine_id : ""}
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0" aria-hidden>
                    <path fillRule="evenodd"
                      d="M10 3a.75.75 0 01.75.75v7.69l2.47-2.47a.75.75 0 111.06 1.06l-3.75 3.75a.75.75 0 01-1.06 0L5.72 10.03a.75.75 0 111.06-1.06L9.25 11.44V3.75A.75.75 0 0110 3zm-6.5 13a.75.75 0 000 1.5h13a.75.75 0 000-1.5h-13z"
                      clipRule="evenodd" />
                  </svg>
                </a>
              </div>
            ))}

            <button onClick={resetar}
              className="w-full py-4 rounded-2xl border border-white/10 text-white/40 font-body text-sm
                         hover:text-white/60 hover:border-white/25 active:scale-95 transition-all duration-150 uppercase tracking-widest">
              Tentar com outra foto
            </button>

            <div className="text-center">
              <p className="font-display text-[#FFD200] text-xl tracking-wider">#BazucadeBolinhas</p>
              <p className="font-display text-white/30 text-base tracking-wider">#HellmannsNBA</p>
            </div>
          </div>
        )}

        {/* ERROR */}
        {phase === "error" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-7 text-center">
            <div className="w-24 h-24 rounded-3xl bg-[#E8003D]/10 border border-[#E8003D]/30 flex items-center justify-center">
              <span className="font-display text-[4rem] text-[#E8003D] leading-none">!</span>
            </div>
            <div className="space-y-2 max-w-xs">
              <h2 className="font-display text-[2rem] tracking-wider text-[#FFD200] leading-none">
                NÃO ENCONTRADO
              </h2>
              <p className="text-white/50 font-body text-sm leading-relaxed">
                {error ?? "Rosto não encontrado. Verifique se o vídeo já foi processado e tente novamente."}
              </p>
            </div>
            <button onClick={resetar}
              className="bg-white text-[#0A0A0A] font-display text-[1.8rem] tracking-wider px-12 py-5 rounded-2xl
                         active:scale-95 transition-all duration-150 uppercase shadow-[0_4px_24px_rgba(0,0,0,0.4)]">
              TENTAR NOVAMENTE
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
