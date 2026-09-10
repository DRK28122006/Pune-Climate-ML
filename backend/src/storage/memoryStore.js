export class MemoryStore {
  constructor() { this.data = { assessments: [], users: [], refreshSessions: [], notifications: [] }; }
  async init() {}
  async listAssessments() { return [...this.data.assessments].sort((a, b) => b.createdAt.localeCompare(a.createdAt)); }
  async getAssessment(id) { return this.data.assessments.find((item) => item.id === id) || null; }
  async saveAssessment(item) { this.data.assessments = [...this.data.assessments.filter((x) => x.id !== item.id), item]; return item; }
  async saveUser(user) { this.data.users = [...this.data.users.filter((x) => x.id !== user.id), user]; return user; }
  async findUserByEmail(email) { return this.data.users.find((user) => user.email.toLowerCase() === email.toLowerCase()) || null; }
  async getUser(id) { return this.data.users.find((user) => user.id === id) || null; }
  async listUsers() { return this.data.users; }
  async saveRefreshSession(session) { this.data.refreshSessions = [...this.data.refreshSessions.filter((x) => x.id !== session.id), session]; }
  async getRefreshSession(id) { return this.data.refreshSessions.find((session) => session.id === id) || null; }
  async deleteRefreshSession(id) { this.data.refreshSessions = this.data.refreshSessions.filter((session) => session.id !== id); }
  async saveNotification(item) { this.data.notifications = [...this.data.notifications.filter((x) => x.id !== item.id), item]; return item; }
  async listNotifications(userId) { return this.data.notifications.filter((item) => item.userId === userId); }
  async markNotificationRead(id, userId) { const item = this.data.notifications.find((x) => x.id === id && x.userId === userId); if (item) item.readAt = new Date().toISOString(); return item || null; }
}
