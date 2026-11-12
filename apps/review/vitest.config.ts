import path from "node:path";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig(async () => {
  // Migration thật của repo, áp lên D1 cục bộ trước mỗi tệp test (test/apply-migrations.ts).
  const migrations = await readD1Migrations(
    path.join(import.meta.dirname, "../../packages/db/migrations"),
  );
  return {
    plugins: [
      cloudflareTest({
        // Không bao giờ gọi tài nguyên Cloudflare thật trong test.
        remoteBindings: false,
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            REVIEW_PASSWORD: "test-password",
            PURGE_TOKEN: "test-purge-token",
          },
          // Worker web giả luôn lỗi: hàng chờ xóa cache còn nguyên để test kiểm. Logic gửi lô
          // được test riêng bằng drainPurgeQueue với một fetcher giả.
          serviceBindings: { WEB: async () => new Response("test", { status: 503 }) },
        },
      }),
    ],
    test: { setupFiles: ["./test/apply-migrations.ts"] },
  };
});
