import "dotenv/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const backendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export const config = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: Number(process.env.PORT || 4000),
  frontendOrigin: process.env.FRONTEND_ORIGIN || "http://localhost:5173",
  authRequired: process.env.AUTH_REQUIRED ? process.env.AUTH_REQUIRED !== "false" : !process.env.VERCEL,
  jwtAccessSecret: process.env.JWT_ACCESS_SECRET || "development-access-secret-change-before-deploy",
  jwtRefreshSecret: process.env.JWT_REFRESH_SECRET || "development-refresh-secret-change-before-deploy",
  accessTokenTtl: process.env.ACCESS_TOKEN_TTL || "15m",
  refreshTokenTtl: process.env.REFRESH_TOKEN_TTL || "7d",
  allowRoleSelfAssignment: process.env.ALLOW_ROLE_SELF_ASSIGNMENT === "true",
  bootstrapAdminEmail: process.env.BOOTSTRAP_ADMIN_EMAIL,
  bootstrapAdminPassword: process.env.BOOTSTRAP_ADMIN_PASSWORD,
  rateLimitWindowMs: Number(process.env.RATE_LIMIT_WINDOW_MS || 900000),
  rateLimitMax: Number(process.env.RATE_LIMIT_MAX || 200),
  authRateLimitMax: Number(process.env.AUTH_RATE_LIMIT_MAX || 20),
  logLevel: process.env.LOG_LEVEL || "info",
  storageDriver: process.env.STORAGE_DRIVER || "file",
  databaseUrl: process.env.DATABASE_URL,
  mlMode: process.env.ML_MODE || "fixture",
  pythonCommand: process.env.PYTHON_COMMAND || "python",
  backendRoot,
  repositoryRoot: path.resolve(backendRoot, ".."),
  dataFile: path.join(backendRoot, "data", "db.json"),
  uploadDirectory: path.join(backendRoot, "uploads"),
  redisUrl: process.env.REDIS_URL,
  fileStorageProvider: process.env.FILE_STORAGE_PROVIDER || "local",
  awsRegion: process.env.AWS_REGION || "ap-south-1",
  awsS3Bucket: process.env.AWS_S3_BUCKET,
  firebaseStorageBucket: process.env.FIREBASE_STORAGE_BUCKET,
  firebaseServiceAccountPath: process.env.FIREBASE_SERVICE_ACCOUNT_PATH,
  smtp: {
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 587),
    secure: process.env.SMTP_SECURE === "true",
    user: process.env.SMTP_USER,
    password: process.env.SMTP_PASSWORD,
    from: process.env.EMAIL_FROM || "climate-platform@example.com",
  },
  twilio: {
    accountSid: process.env.TWILIO_ACCOUNT_SID,
    authToken: process.env.TWILIO_AUTH_TOKEN,
    fromNumber: process.env.TWILIO_FROM_NUMBER,
  },
};

if (config.nodeEnv === "production" && config.authRequired) {
  if (config.jwtAccessSecret.startsWith("development-") || config.jwtRefreshSecret.startsWith("development-")) {
    throw new Error("JWT_ACCESS_SECRET and JWT_REFRESH_SECRET must be set in production");
  }
}
