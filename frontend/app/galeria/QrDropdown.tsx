"use client";

import { useState } from "react";

interface QrDropdownProps {
  qrUrl: string;
  cabineId: number;
}

export function QrDropdown({ qrUrl, cabineId }: QrDropdownProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-white/10">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between w-full px-5 py-4 text-left
                   bg-white/[0.03] hover:bg-white/[0.07] transition-colors duration-150"
      >
        <div className="flex items-center gap-2.5">
          {/* QR icon */}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
            className="w-5 h-5 text-[#FFD200] flex-shrink-0">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 013.75 9.375v-4.5zM3.75 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0113.5 9.375v-4.5z" />
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M6.75 6.75h.75v.75h-.75v-.75zM6.75 16.5h.75v.75h-.75V16.5zM16.5 6.75h.75v.75h-.75v-.75zM13.5 13.5h.75v.75h-.75v-.75zM13.5 19.5h.75v.75h-.75v-.75zM19.5 13.5h.75v.75h-.75v-.75zM19.5 19.5h.75v.75h-.75v-.75zM16.5 16.5h.75v.75h-.75v-.75z" />
          </svg>
          <span className="font-display text-white tracking-[0.2em] text-base">
            QR CODE — CABINE {cabineId}
          </span>
        </div>
        {/* chevron */}
        <svg viewBox="0 0 20 20" fill="currentColor"
          className={`w-4 h-4 text-white/30 flex-shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          <path fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className="flex flex-col items-center gap-4 px-5 py-6 bg-black/40 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qrUrl}
            alt={`QR Code para o vídeo da Cabine ${cabineId}`}
            className="w-48 h-48 bg-white rounded-2xl p-3 shadow-[0_0_40px_rgba(255,210,0,0.15)]"
          />
          <p className="text-white/35 font-body text-xs max-w-[200px] leading-snug">
            Escaneie para baixar direto o vídeo da Cabine {cabineId}
          </p>
        </div>
      )}
    </div>
  );
}
