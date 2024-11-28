const menu = {
    "🍔 *HAMBURGUESAS*": {
        "clasica": {"precio": 5.00, "codigo": 301},
        "ranchera": {"precio": 5.50, "codigo": 302},
        "crispy": {"precio": 6.00, "codigo": 303}
    },
    "🌭 *PERRITOS*": {
        "clasico": {"precio": 4.00, "codigo": 401},
        "picanton": {"precio": 4.00, "codigo": 402},
        "texano": {"precio": 4.00, "codigo": 403},
        "bbq": {"precio": 4.00, "codigo": 404}
    },
    "🍨 *POSTRES*": {
        "flan": {"precio": 4.00, "codigo": 501},
        "tarta": {"precio": 5.00, "codigo": 502},
        "helado": {"precio": 3.50, "codigo": 503}
    },
    "🥤 *BEBIDAS*": {
        "agua": {"precio": 1.50, "codigo": 601},
        "vino": {"precio": 4.00, "codigo": 602},
        "cerveza": {"precio": 3.00, "codigo": 603},
        "refresco": {"precio": 2.50, "codigo": 604},
        "café": {"precio": 2.00, "codigo": 605}
    }
};
const menuDiv = document.getElementById('menu');
const phone = "{{ usuario.numero_cliente }}"; // Teléfono proporcionado desde Flask
// Crear elementos dinámicos del menú
Object.keys(menu).forEach(category => {
    const categoryDiv = document.createElement('div');
    categoryDiv.innerHTML = `<h2>${category}</h2>`;
    Object.keys(menu[category]).forEach(item => {
        const { precio } = menu[category][item];
        const itemDiv = document.createElement('div');
        itemDiv.className = 'menu-item';
        itemDiv.innerHTML = `
            <span>${item} - $${precio.toFixed(2)}</span>
            <div class="quantity-control">
                <button class="decrease" data-item="${item}" disabled>-</button>
                <span class="quantity-display" id="quantity-${item}">0</span>
                <button class="increase" data-item="${item}">+</button>
            </div>
        `;
        categoryDiv.appendChild(itemDiv);
    });
    menuDiv.appendChild(categoryDiv);
});
const quantities = {};
// Controlar la cantidad de productos
document.addEventListener('click', (event) => {
    if (event.target.classList.contains('increase') || event.target.classList.contains('decrease')) {
        event.preventDefault();
        const item = event.target.dataset.item;
        if (!quantities[item]) quantities[item] = 0;
        if (event.target.classList.contains('increase')) {
            quantities[item]++;
        } else if (event.target.classList.contains('decrease')) {
            quantities[item] = Math.max(0, quantities[item] - 1);
        }
        // Actualizar la interfaz
        document.getElementById(`quantity-${item}`).innerText = quantities[item];
        const decreaseButton = event.target.closest('.quantity-control').querySelector('.decrease');
        decreaseButton.disabled = quantities[item] === 0;
    }
});
document.getElementById('submitOrder').addEventListener('click', async () => {
    // Capturamos el teléfono del usuario proporcionado por Flask
    const phone = `{{ usuario.numero_cliente }}`;
    // Filtramos y transformamos los productos seleccionados
    const selectedItems = Object.entries(quantities)
        .filter(([_, quantity]) => quantity > 0)
        .map(([item, quantity]) => {
            const category = Object.keys(menu).find(cat => menu[cat][item]);
            const { precio } = menu[category][item];
            return [item, precio]; // Formato requerido: [item, precio]
        });
    // Validación: asegurarnos de que haya al menos un producto seleccionado
    if (selectedItems.length === 0) {
        alert('Por favor, selecciona al menos un producto.');
        return;
    }
    // Crear el objeto del pedido
    const order = {
        [phone]: selectedItems
    };
    // Enviar el pedido al servidor
    try {
        const response = await fetch('http://127.0.0.1:5000/api/agregar_pedido', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(order)
        });
        if (response.ok) {
            const result = await response.json();
            alert(result.message || 'Pedido enviado correctamente.');
        } else {
            const error = await response.json();
            alert('Error al enviar el pedido: ' + (error.message || 'Desconocido'));
        }
    } catch (err) {
        console.error('Error de conexión:', err);
        alert('No se pudo conectar con el servidor. Inténtalo de nuevo.');
    }
});