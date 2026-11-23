/// Metin2-Multiversum – Abgleich der App-Daten über den eigenen Server
/// Nutzt dieselben Konten ("users") wie TCG Multiversum.
/// - m2_sync: je Konto ein Datensatz mit allen App-Daten, nur für das eigene Konto sichtbar
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  const col = new Collection({
    type: "base",
    name: "m2_sync",
    listRule: "owner = @request.auth.id",
    viewRule: "owner = @request.auth.id",
    createRule: '@request.auth.id != "" && @request.body.owner = @request.auth.id',
    updateRule: "owner = @request.auth.id && (@request.body.owner:isset = false || @request.body.owner = @request.auth.id)",
    deleteRule: "owner = @request.auth.id",
    fields: [
      { type: "relation", name: "owner", collectionId: users.id, maxSelect: 1, required: true, cascadeDelete: true },
      { type: "json", name: "payload", maxSize: 20000000 },
      { type: "autodate", name: "created", onCreate: true, onUpdate: false },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_m2_sync_owner ON m2_sync (owner)"],
  });
  app.save(col);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("m2_sync")); } catch (e) {}
});
