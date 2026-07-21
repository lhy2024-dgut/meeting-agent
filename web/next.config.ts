import type { NextConfig } from "next";

// 后端地址（默认本地）。把 /api/* 反向代理到后端，使浏览器对后端的请求变为
// 同源（都走 localhost:3000），彻底避免跨域预检与浏览器对本地回环端口的连接限制。
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
