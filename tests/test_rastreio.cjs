const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function armazenamento() {
  const dados = new Map();
  return { getItem: k => dados.get(k) || null, setItem: (k, v) => dados.set(k, v),
    removeItem: k => dados.delete(k) };
}

async function main() {
  const localStorage = armazenamento(), sessionStorage = armazenamento();
  const pendentes = [];
  const resposta = { ok: true, json: () => Promise.resolve({ ok: true }) };
  const ctx = { localStorage, sessionStorage, window: {}, URLSearchParams, setTimeout,
    document: { currentScript: null, referrer: "" }, location: { search: "", hostname: "loja.test" },
    fetch: url => url === "/api/evento"
      ? new Promise((resolve, reject) => pendentes.push({ resolve, reject }))
      : Promise.resolve(resposta) };
  vm.runInNewContext(fs.readFileSync("web/rastreio.js", "utf8"), ctx);
  const rastreio = ctx.window.Rastreio;
  const primeira = rastreio.aceitar({}), segunda = rastreio.aceitar({});
  await new Promise(setImmediate);
  assert.equal(pendentes.length, 1, "chamadas simultâneas compartilham a visita");
  await rastreio.revogar();
  pendentes[0].resolve(resposta);
  await Promise.all([primeira, segunda]);
  assert.equal(sessionStorage.getItem("atrib_sessao"), null, "resposta antiga não restaura a sessão");
  const nova = rastreio.aceitar({});
  await new Promise(setImmediate);
  assert.equal(pendentes.length, 2, "novo consentimento envia uma nova visita");
  pendentes[1].resolve(resposta);
  await nova;
  assert.equal(sessionStorage.getItem("atrib_sessao"), "1");

  await rastreio.revogar();
  const repetida = rastreio.aceitar({});
  await new Promise(setImmediate);
  pendentes[2].reject(new Error("resposta perdida"));
  await new Promise(resolve => setTimeout(resolve, 600));
  assert.equal(pendentes.length, 4, "erro de rede provoca nova tentativa");
  pendentes[3].resolve(resposta);
  await repetida;
  assert.equal(sessionStorage.getItem("atrib_sessao"), "1");
}

main().catch(erro => { console.error(erro); process.exitCode = 1; });
