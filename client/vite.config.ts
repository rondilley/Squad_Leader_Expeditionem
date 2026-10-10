import { defineConfig } from "vite";

// The host serves the built files from client/dist on its own port, so the base is
// relative and the build has no hashed directory.
export default defineConfig({
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
  },
  server: {
    port: 5173,
  },
});
