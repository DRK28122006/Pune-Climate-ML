import crypto from "node:crypto";
import express from "express";
import cors from "cors";
import helmet from "helmet";
import multer from "multer";
import { rateLimit } from "express-rate-limit";
import { ZodError } from "zod";
import {
  assessmentInput, loginInput, notificationInput, refreshInput, registerInput, reassessmentInput,
} from "./validation.js";
import { buildProject, createAssessment } from "./services/assessmentService.js";
import { optimizeProject, toApiAssessment } from "./services/recommendationService.js";
import { streamAssessmentReport } from "./services/reportService.js";
import { ADMIN_ROLES, WRITE_ROLES, authenticate, authorize, canAccessAssessment } from "./middleware/auth.js";
import { createRequestLogger } from "./middleware/requestLogger.js";

const asyncRoute = (handler) => (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);

function visibleProjects(user, projects) {
  return projects.filter((project) => canAccessAssessment(user, project));
}

function requireProject(store) {
  return asyncRoute(async (req, res, next) => {
    const project = await store.getAssessment(req.params.id);
    if (!project) return res.status(404).json({ error: "Assessment not found" });
    if (!canAccessAssessment(req.user, project)) return res.status(403).json({ error: "Assessment access denied" });
    req.project = project;
    next();
  });
}

export function createApp({ config, store, authService, objectStorage, jobQueue = null, notificationService = null }) {
  const app = express();
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 20 * 1024 * 1024, files: 5 },
    fileFilter: (_req, file, callback) => {
      const allowed = new Set(["application/pdf", "image/png", "image/jpeg", "text/csv", "application/vnd.ms-excel"]);
      if (allowed.has(file.mimetype)) return callback(null, true);
      const error = new Error("Unsupported file type");
      error.status = 400;
      callback(error, false);
    },
  });
  const apiLimiter = rateLimit({
    windowMs: config.rateLimitWindowMs,
    limit: config.rateLimitMax,
    standardHeaders: "draft-8",
    legacyHeaders: false,
    skip: (req) => req.path === "/api/health",
  });
  const authLimiter = rateLimit({
    windowMs: config.rateLimitWindowMs,
    limit: config.authRateLimitMax,
    standardHeaders: "draft-8",
    legacyHeaders: false,
  });
  const authenticated = config.authRequired
    ? authenticate(authService)
    : (req, _res, next) => { req.user = { sub: "development-user", role: "admin", email: "dev@local" }; next(); };

  app.disable("x-powered-by");
  app.use(createRequestLogger(config));
  app.use(helmet());
  app.use(cors({ origin: config.frontendOrigin, exposedHeaders: ["x-request-id", "ratelimit"] }));
  app.use(express.json({ limit: "1mb" }));
  app.use("/api", apiLimiter);

  app.get("/api/health", (_req, res) => res.json({
    status: "ok",
    mlMode: config.mlMode,
    database: config.storageDriver,
    fileStorage: config.fileStorageProvider,
    queues: jobQueue?.enabled ? "redis" : "synchronous",
  }));

  app.post("/api/v1/auth/register", authLimiter, asyncRoute(async (req, res) => {
    const user = await authService.register(registerInput.parse(req.body));
    res.status(201).json({ user });
  }));
  app.post("/api/v1/auth/login", authLimiter, asyncRoute(async (req, res) => {
    res.json(await authService.login(loginInput.parse(req.body)));
  }));
  app.post("/api/v1/auth/refresh", authLimiter, asyncRoute(async (req, res) => {
    const { refreshToken } = refreshInput.parse(req.body);
    res.json(await authService.refresh(refreshToken));
  }));
  app.post("/api/v1/auth/logout", asyncRoute(async (req, res) => {
    const { refreshToken } = refreshInput.parse(req.body);
    await authService.logout(refreshToken);
    res.status(204).end();
  }));

  app.use("/api/v1", authenticated);

  app.get("/api/v1/users", authorize(...ADMIN_ROLES), asyncRoute(async (_req, res) => {
    const users = await store.listUsers();
    res.json({ items: users.map(({ passwordHash: _passwordHash, ...user }) => user), count: users.length });
  }));
  app.post("/api/v1/users", authorize(...ADMIN_ROLES), asyncRoute(async (req, res) => {
    const user = await authService.register(registerInput.parse(req.body), { createdByAdmin: true });
    res.status(201).json({ user });
  }));

  app.get("/api/v1/assessments", asyncRoute(async (req, res) => {
    const projects = visibleProjects(req.user, await store.listAssessments());
    res.json({ items: projects.map(toApiAssessment), count: projects.length });
  }));

  app.post("/api/v1/assessments", authorize(...WRITE_ROLES), asyncRoute(async (req, res) => {
    const input = assessmentInput.parse(req.body);
    if (req.query.async === "true") {
      if (!jobQueue?.enabled) return res.status(503).json({ error: "REDIS_URL is required for asynchronous analysis" });
      const job = await jobQueue.addAssessment({ input, ownerId: req.user.sub });
      return res.status(202).json({ jobId: job.id, statusUrl: `/api/v1/jobs/assessment-analysis/${job.id}` });
    }
    const project = await createAssessment({ input, ownerId: req.user.sub, config, store, notificationService });
    if (req.query.includeOptimization === "true") {
      return res.status(201).json({ assessment: toApiAssessment(project), optimization: optimizeProject(project) });
    }
    res.status(201).json(toApiAssessment(project));
  }));

  app.get("/api/v1/assessments/:id", requireProject(store), (req, res) => res.json(toApiAssessment(req.project)));

  app.post("/api/v1/assessments/:id/optimize", authorize(...WRITE_ROLES), requireProject(store), (req, res) => {
    res.json(optimizeProject(req.project));
  });

  app.post("/api/v1/assessments/:id/reassess", authorize(...WRITE_ROLES), requireProject(store), asyncRoute(async (req, res) => {
    const changes = reassessmentInput.parse(req.body);
    const input = {
      ...req.project.input,
      materials: changes.materials ?? req.project.input.materials,
      builtUpAreaSqm: changes.builtUpAreaSqm ?? req.project.input.builtUpAreaSqm,
    };
    const updated = buildProject(input, changes.mlOutput ?? req.project.mlOutput, req.project);
    await store.saveAssessment(updated);
    res.json(toApiAssessment(updated));
  }));

  app.post("/api/v1/assessments/:id/documents", authorize(...WRITE_ROLES), requireProject(store), upload.array("documents", 5), asyncRoute(async (req, res) => {
    if (!req.files?.length) return res.status(400).json({ error: "At least one documents file is required" });
    const documents = await Promise.all(req.files.map(async (file) => {
      const stored = await objectStorage.save(file, req.project.id);
      return {
        id: crypto.randomUUID(), name: file.originalname, mimeType: file.mimetype,
        size: file.size, storageKey: stored.key, provider: stored.provider, uploadedAt: new Date().toISOString(),
      };
    }));
    req.project.documents = [...(req.project.documents || []), ...documents];
    req.project.updatedAt = new Date().toISOString();
    await store.saveAssessment(req.project);
    res.status(201).json({ items: documents.map(({ storageKey: _storageKey, ...document }) => document) });
  }));

  app.get("/api/v1/assessments/:id/documents/:documentId", requireProject(store), asyncRoute(async (req, res) => {
    const document = req.project.documents?.find((item) => item.id === req.params.documentId);
    if (!document) return res.status(404).json({ error: "Document not found" });
    res.type(document.mimeType);
    res.setHeader("Content-Disposition", `attachment; filename="${encodeURIComponent(document.name)}"`);
    const stream = await objectStorage.get(document.storageKey || document.id);
    stream.on("error", (error) => req.log.error(error));
    stream.pipe(res);
  }));

  app.get("/api/v1/assessments/:id/report", requireProject(store), (req, res) => {
    streamAssessmentReport(res, toApiAssessment(req.project));
  });

  app.get("/api/v1/dashboard", asyncRoute(async (req, res) => {
    const items = visibleProjects(req.user, await store.listAssessments()).map(toApiAssessment);
    const average = items.length ? items.reduce((sum, item) => sum + item.impactScore, 0) / items.length : 0;
    res.json({
      activeProjects: items.length,
      averageImpactScore: Number(average.toFixed(1)),
      highRiskSites: items.filter((item) => item.status === "High").length,
      recentAssessments: items.slice(0, 5),
    });
  }));

  app.get("/api/v1/notifications", asyncRoute(async (req, res) => {
    const items = await store.listNotifications(req.user.sub);
    res.json({ items, unread: items.filter((item) => !item.readAt).length });
  }));
  app.patch("/api/v1/notifications/:id/read", asyncRoute(async (req, res) => {
    const item = await store.markNotificationRead(req.params.id, req.user.sub);
    if (!item) return res.status(404).json({ error: "Notification not found" });
    res.json(item);
  }));
  app.post("/api/v1/notifications", authorize(...ADMIN_ROLES), asyncRoute(async (req, res) => {
    const notification = await notificationService.create(notificationInput.parse(req.body));
    res.status(201).json(notification);
  }));

  app.get("/api/v1/jobs/:queue/:id", asyncRoute(async (req, res) => {
    if (!jobQueue?.enabled) return res.status(503).json({ error: "Redis jobs are not enabled" });
    const status = await jobQueue.status(req.params.queue, req.params.id);
    if (!status) return res.status(404).json({ error: "Job not found" });
    if (!ADMIN_ROLES.includes(req.user.role) && status.ownerId !== req.user.sub) {
      return res.status(403).json({ error: "Job access denied" });
    }
    const { ownerId: _ownerId, ...safeStatus } = status;
    res.json(safeStatus);
  }));

  app.use((_req, res) => res.status(404).json({ error: "Route not found" }));
  app.use((error, req, res, _next) => {
    if (error instanceof ZodError) return res.status(400).json({ error: "Validation failed", details: error.issues });
    if (error instanceof multer.MulterError) return res.status(400).json({ error: error.message });
    req.log?.error(error);
    const status = error.status || 500;
    res.status(status).json({ error: status === 500 && config.nodeEnv === "production" ? "Internal server error" : error.message });
  });
  return app;
}
