export async function createStore(config) {
  if (config.storageDriver === "memory") {
    const { MemoryStore } = await import("./memoryStore.js");
    const store = new MemoryStore();
    await store.init();
    return store;
  }
  if (config.storageDriver === "postgres") {
    if (!config.databaseUrl) throw new Error("DATABASE_URL is required for PostgreSQL storage");
    const { PostgresStore } = await import("./postgresStore.js");
    const store = new PostgresStore(config.databaseUrl);
    await store.init();
    return store;
  }
  const { FileStore } = await import("./fileStore.js");
  const store = new FileStore(config.dataFile);
  await store.init();
  return store;
}
