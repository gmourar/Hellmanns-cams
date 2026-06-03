import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/operator/:path*",  destination: `${BACKEND}/operator/:path*`  },
      { source: "/agent/:path*",     destination: `${BACKEND}/agent/:path*`      },
      { source: "/gallery/:path*",   destination: `${BACKEND}/gallery/:path*`    },
      { source: "/videos/:path*",    destination: `${BACKEND}/videos/:path*`     },
      { source: "/sessions",         destination: `${BACKEND}/sessions`          },
      { source: "/buscar-video",     destination: `${BACKEND}/buscar-video`      },
      { source: "/meu-video/:path*", destination: `${BACKEND}/meu-video/:path*`  },
      { source: "/admin/stats",      destination: `${BACKEND}/admin/stats`        },
    ];
  },
};

export default nextConfig;
