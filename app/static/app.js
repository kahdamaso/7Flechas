/* TUC7FJ — comportamento das telas usadas por vários aparelhos ao mesmo tempo.
 *
 * 1. <form data-ajax>: envia sem recarregar a página (toque rápido na chamada).
 *    Sem JavaScript, o formulário funciona do jeito normal.
 * 2. <div id="..." data-atualizar="10">: a cada N segundos busca a página de
 *    novo e troca só o conteúdo desse bloco, mostrando o que outros aparelhos
 *    registraram. Não atualiza enquanto a pessoa está digitando nele.
 */
(function () {
  'use strict';

  var ocupado = false;

  function blocosAtualizaveis() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-atualizar][id]'));
  }

  function digitandoEm(bloco) {
    var ativo = document.activeElement;
    return ativo && bloco.contains(ativo) && /^(INPUT|TEXTAREA|SELECT)$/.test(ativo.tagName) &&
      ativo.type !== 'submit' && ativo.type !== 'button';
  }

  function atualizar(forcar) {
    if (ocupado || (document.hidden && !forcar)) { return Promise.resolve(); }
    var blocos = blocosAtualizaveis().filter(function (b) { return forcar || !digitandoEm(b); });
    if (!blocos.length) { return Promise.resolve(); }
    ocupado = true;
    return fetch(window.location.href, { headers: { 'X-Requested-With': 'fetch-parcial' }, credentials: 'same-origin' })
      .then(function (resp) {
        if (resp.redirected || !resp.ok) { throw new Error('sessão'); }
        return resp.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        blocos.forEach(function (bloco) {
          var novo = doc.getElementById(bloco.id);
          if (novo && novo.innerHTML !== bloco.innerHTML) { bloco.innerHTML = novo.innerHTML; }
        });
      })
      .catch(function () { /* sem rede ou sessão expirada: tenta no próximo ciclo */ })
      .then(function () { ocupado = false; });
  }

  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form.hasAttribute('data-ajax') || !window.fetch) { return; }
    ev.preventDefault();
    var dados = new FormData(form);
    if (ev.submitter && ev.submitter.name) { dados.set(ev.submitter.name, ev.submitter.value); }
    form.classList.add('enviando');
    Array.prototype.forEach.call(form.querySelectorAll('button'), function (b) { b.disabled = true; });
    fetch(form.action, {
      method: 'POST', body: dados, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    })
      .then(function (resp) {
        if (!resp.ok) { throw new Error(resp.status); }
        return atualizar(true);
      })
      .catch(function () {
        alert('Não foi possível salvar. Verifique a conexão e tente de novo.');
        Array.prototype.forEach.call(form.querySelectorAll('button'), function (b) { b.disabled = false; });
      })
      .then(function () { form.classList.remove('enviando'); });
  });

  blocosAtualizaveis().forEach(function (bloco) {
    var segundos = parseInt(bloco.getAttribute('data-atualizar'), 10) || 10;
    setInterval(atualizar, segundos * 1000);
  });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { atualizar(); }
  });
})();
