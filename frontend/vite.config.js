import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    
    // 환경변수에서 설정 값 가져오기 (기본값 포함)
    const frontendHost = env.FRONTEND_HOST || "0.0.0.0";
    const frontendPort = parseInt(env.FRONTEND_PORT) || 32376;
    const backendUrl = env.BACKEND_URL || "http://127.0.0.1:32375";
    
    return {
        plugins: [sveltekit()],
        server: {
            host: frontendHost,
            port: frontendPort,
            proxy: {
                "/api": {
                    target: backendUrl,
                    changeOrigin: true,
                },
            },
        },
        define: {
            // 클라이언트에서 사용할 환경변수 정의
            __BACKEND_URL__: JSON.stringify(backendUrl),
            __FRONTEND_URL__: JSON.stringify(env.FRONTEND_URL || `http://localhost:${frontendPort}`),
            __PRODUCTION_BACKEND_URL__: JSON.stringify(env.PRODUCTION_BACKEND_URL || ""),
            __PRODUCTION_FRONTEND_URL__: JSON.stringify(env.PRODUCTION_FRONTEND_URL || ""),
            __ENVIRONMENT__: JSON.stringify(env.ENVIRONMENT || "development"),
        },
    };
});
