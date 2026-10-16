(() => {
  const form = document.getElementById('waiterForm');
  const grid = document.querySelector('.waiter-grid');
  const hiddenBox = document.getElementById('waiterHiddenInputs');
  const cartList = document.getElementById('waiterCartList');
  const cartEmpty = document.getElementById('waiterCartEmpty');
  const cartCount = document.getElementById('waiterCartCount');
  const clearBtn = document.getElementById('waiterClear');
  const submitBtn = document.getElementById('waiterSubmit');

  if (!form || !grid) return;

  const cart = new Map();

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function render() {
    hiddenBox.innerHTML = '';
    cart.forEach((item) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = `dish_${item.id}`;
      input.value = String(item.qty);
      hiddenBox.appendChild(input);
    });

    cartList.innerHTML = '';
    let total = 0;
    cart.forEach((item) => {
      total += item.qty;
      const li = document.createElement('li');
      li.innerHTML = `
        <span class="cart-name">${escapeHtml(item.name)}</span>
        <span class="cart-controls">
          <button type="button" data-act="dec" data-id="${item.id}">−</button>
          <span class="cart-qty">${item.qty}</span>
          <button type="button" data-act="inc" data-id="${item.id}">+</button>
        </span>`;
      cartList.appendChild(li);
    });

    cartEmpty.classList.toggle('hidden', cart.size > 0);
    cartCount.textContent = String(total);
    submitBtn.disabled = cart.size === 0;
  }

  function addDish(btn) {
    const id = Number(btn.dataset.id);
    const name = btn.dataset.name;
    const max = Number(btn.dataset.portions) || 0;
    if (!id || max <= 0) return;
    const current = cart.get(id);
    if (current) {
      if (current.qty < max) current.qty += 1;
    } else {
      cart.set(id, { id, name, qty: 1, max });
    }
    render();
  }

  function changeQty(id, delta) {
    const item = cart.get(id);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) cart.delete(id);
    if (item.qty > item.max) item.qty = item.max;
    render();
  }

  grid.addEventListener('click', (e) => {
    const btn = e.target.closest('.waiter-dish');
    if (!btn || btn.disabled) return;
    addDish(btn);
  });

  cartList.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const act = btn.dataset.act;
    changeQty(id, act === 'inc' ? 1 : -1);
  });

  clearBtn?.addEventListener('click', () => {
    cart.clear();
    render();
  });

  render();
})();