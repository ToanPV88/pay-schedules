// Cho TypeScript biết module chính của Worker, để `exports.default` và `env` có kiểu đúng.
import type * as main from "../src/index";

declare global {
  namespace Cloudflare {
    interface GlobalProps {
      mainModule: typeof main;
    }
    interface Env extends main.Env {}
  }
}
