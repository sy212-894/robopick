import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중에는 /api 요청을 중계 서버(webapi, 127.0.0.1:8900)로 넘긴다.
// 빌드 결과는 OneDrive 밖에 쓴다: 저장소가 OneDrive 안에 있어 web/dist에 쓰면 동기화 중인 파일과 부딪혀
// 빌드가 비정상 종료(0xC0000409)됐다 (2026-10-12). 중계 서버(webapi/config.py)도 같은 위치를 읽는다
const OUT_DIR = process.env.WEB_DIST ?? 'C:/curation-data/web-dist'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: OUT_DIR, emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8900', changeOrigin: true },
    },
  },
})
