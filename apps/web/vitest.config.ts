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
        // Test gọi bằng https://example.invalid: tắt chuyển về tên miền chính (D-113).
        miniflare: { bindings: { TEST_MIGRATIONS: migrations, CANONICAL_ORIGIN: "" } },
      }),
    ],
    test: { setupFiles: ["./test/apply-migrations.ts"] },
  };
});
