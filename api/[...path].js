import { createApp } from "../backend/src/app.js";
import { config as baseConfig } from "../backend/src/config.js";
import { createStore } from "../backend/src/storage/index.js";
import { AuthService } from "../backend/src/services/authService.js";
import crypto from "node:crypto";
import { Readable } from "node:stream";

const config = {
  ...baseConfig,
  authRequired: process.env.AUTH_REQUIRED === "true",
  storageDriver: process.env.DATABASE_URL ? "postgres" : "memory",
  fileStorageProvider: "memory",
  frontendOrigin: process.env.FRONTEND_ORIGIN || true,
  mlMode: process.env.ML_MODE || "fixture",
};

const store = await createStore(config);
const files = new Map();
const objectStorage = {
  async save(file, assessmentId) {
    const key = `${assessmentId}/${crypto.randomUUID()}-${file.originalname}`;
    files.set(key, file.buffer);
    return { key, provider: "memory" };
  },
  async get(key) {
    const file = files.get(key);
    if (!file) { const error = new Error("Document not found"); error.status = 404; throw error; }
    return Readable.from(file);
  },
};
const authService = new AuthService({ config, store });
await authService.ensureBootstrapAdmin();

export default createApp({ config, store, authService, objectStorage });
