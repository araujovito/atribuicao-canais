/*
 * Rastreador do lado do navegador.
 *
 * Nada é gravado nem enviado antes do "sim" no banner: o identificador do
 * aparelho (anon_id) só é criado depois do consentimento. A única coisa
 * guardada sem consentimento é a própria resposta "não", para não perguntar
 * de novo a cada página (armazenamento estritamente necessário).
 *
 * Só a visita de ENTRADA de cada sessão é enviada, porque é ela que carrega a
 * origem (UTM, referrer, gclid). Página a página dentro do site não serve para
 * atribuição e não sai do navegador.
 *
 * Uso: <script src="/web/rastreio.js"></script> e depois
 *   Rastreio.aceitar() / Rastreio.recusar() / Rastreio.revogar()
 *   Rastreio.identificar(email)       (login ou formulário)
 *   Rastreio.converter(valor, email)  (compra)
 */
(function () {
  "use strict";

  var VERSAO_TEXTO = "v1"; // versão do texto do banner; mudou o texto, muda aqui
  var CHAVE_CONSENT = "atrib_consentimento";
  var CHAVE_ANON = "atrib_anon";
  var CHAVE_SESSAO = "atrib_sessao";
  var API = (document.currentScript && document.currentScript.dataset.api) || "";

  function ler(chave, armazenamento) {
    try { return (armazenamento || localStorage).getItem(chave); } catch (e) { return null; }
  }
  function gravar(chave, valor, armazenamento) {
    try { (armazenamento || localStorage).setItem(chave, valor); } catch (e) { /* modo privado */ }
  }
  function apagar(chave) {
    try { localStorage.removeItem(chave); } catch (e) { /* idem */ }
  }

  function enviar(rota, dados, metodo) {
    return fetch(API + rota, {
      method: metodo || "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados),
      keepalive: true,
    }).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }

  function novoId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "x" + Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function consentiu() { return ler(CHAVE_CONSENT) === "sim"; }
  function anonId() { return consentiu() ? ler(CHAVE_ANON) : null; }

  function visitaDeEntrada() {
    if (!consentiu() || ler(CHAVE_SESSAO, sessionStorage)) return Promise.resolve(null);
    gravar(CHAVE_SESSAO, "1", sessionStorage);
    var q = new URLSearchParams(location.search);
    return enviar("/api/evento", {
      anon_id: anonId(),
      tipo: "visita",
      host: location.hostname,
      referrer: document.referrer || null,
      utm_source: q.get("utm_source"),
      utm_medium: q.get("utm_medium"),
      utm_campaign: q.get("utm_campaign"),
      gclid: q.get("gclid"),
    });
  }

  var Rastreio = {
    estado: function () {
      var c = ler(CHAVE_CONSENT);
      return { consentimento: c === "sim" ? "aceito" : c === "nao" ? "recusado" : "pendente", anon_id: anonId() };
    },

    aceitar: function () {
      var id = ler(CHAVE_ANON) || novoId();
      gravar(CHAVE_ANON, id);
      gravar(CHAVE_CONSENT, "sim");
      return enviar("/api/consentimento", { anon_id: id, aceito: true, versao: VERSAO_TEXTO }).then(visitaDeEntrada);
    },

    recusar: function () {
      gravar(CHAVE_CONSENT, "nao");
      return Promise.resolve();
    },

    // Revogar é tão fácil quanto aceitar (LGPD art. 8º, §5º): registra o "não"
    // no servidor e esquece o identificador neste aparelho.
    revogar: function () {
      var id = ler(CHAVE_ANON);
      gravar(CHAVE_CONSENT, "nao");
      apagar(CHAVE_ANON);
      if (!id) return Promise.resolve();
      return enviar("/api/consentimento", { anon_id: id, aceito: false, versao: VERSAO_TEXTO });
    },

    identificar: function (email) {
      if (!consentiu()) return Promise.resolve(null);
      return enviar("/api/identificar", { anon_id: anonId(), email: email });
    },

    converter: function (valor, email) {
      if (!consentiu()) return Promise.resolve(null);
      return enviar("/api/evento", { anon_id: anonId(), tipo: "conversao", valor: valor, email: email || null });
    },

    excluirMeusDados: function (email) {
      return enviar("/api/titular", { email: email }, "DELETE").then(function (r) {
        return Rastreio.revogar().then(function () { return r; });
      });
    },
  };

  window.Rastreio = Rastreio;
  visitaDeEntrada();
})();
