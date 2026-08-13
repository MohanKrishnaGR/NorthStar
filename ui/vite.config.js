import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base "./" so the built assets resolve from any directory; tools/build_ui.py
// then inlines everything into a single explorer_template.html.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", assetsInlineLimit: 0 },
});
