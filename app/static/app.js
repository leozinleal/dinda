// Comportamentos da interface (sem scripts embutidos no HTML, para permitir a política de segurança CSP).

// Confirmação antes de excluir
document.addEventListener('submit', function (e) {
  const msg = e.target.dataset.confirmar;
  if (msg && !confirm(msg)) e.preventDefault();
});

// Selects que enviam o filtro ao mudar e botões de imprimir
document.addEventListener('change', function (e) {
  if (e.target.matches('[data-autoenviar]')) e.target.form.submit();
});
document.addEventListener('click', function (e) {
  if (e.target.closest('[data-imprimir]')) window.print();
});

// Troca a lista de categorias conforme entrada/saída
document.querySelectorAll('[data-categorias]').forEach(function (sel) {
  const tipo = document.querySelector(sel.dataset.categorias);
  const atualizar = function () {
    const t = tipo.type === 'radio' ? document.querySelector(sel.dataset.categorias + ':checked').value : tipo.value;
    sel.querySelectorAll('optgroup').forEach(function (g) {
      const mostra = g.dataset.tipo === t;
      g.hidden = !mostra; g.disabled = !mostra;
    });
    const atual = sel.selectedOptions[0];
    if (atual && atual.parentElement.disabled) sel.value = '';
  };
  document.querySelectorAll(sel.dataset.categorias).forEach(function (el) { el.addEventListener('change', atualizar); });
  atualizar();
});

// Abas: lembra a aba aberta no endereço (#aba) para voltar a ela depois de salvar ou recarregar.
(function () {
  const abas = document.querySelectorAll('[data-bs-toggle="tab"]');
  if (!abas.length) return;
  const alvo = location.hash && document.querySelector('[data-bs-target="' + location.hash + '"]');
  if (alvo) bootstrap.Tab.getOrCreateInstance(alvo).show();
  abas.forEach(function (a) {
    a.addEventListener('shown.bs.tab', function () { history.replaceState(null, '', a.dataset.bsTarget); });
  });
})();
