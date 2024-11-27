document.getElementById('quiniela-form').addEventListener('submit', async function (e) {
    e.preventDefault();

    // Obtener los productos seleccionados
    const selectedProducts = [...document.querySelectorAll('input[name="productos"]:checked')].map(input => input.value);

    // Obtener el número de WhatsApp
    const numeroWhatsApp = document.getElementById('numero_whatsapp').value;

    if (selectedProducts.length === 0) {
        alert('Por favor selecciona al menos un producto.');
        return;
    }

    // Construir los datos en el formato esperado por la API
    const productos = selectedProducts.map(product => {
        for (let category in menu) {
            for (let item in menu[category]) {
                if (product.toLowerCase().includes(item)) {
                    return [item, menu[category][item].precio]; // Formato esperado: (nombre, precio)
                }
            }
        }
        return null;
    }).filter(item => item !== null);

    const payload = {
        [`whatsapp:${numeroWhatsApp}`]: productos
    };

    try {
        // Llamar a la API para agregar el pedido
        const response = await fetch('http://127.0.0.1:5000/api/agregar_pedido', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status}`);
        }

        const result = await response.json();
        alert(result.message);
    } catch (error) {
        console.error('Error al enviar el pedido:', error);
        alert('Hubo un problema al procesar el pedido. Por favor, intenta de nuevo.');
    }
});
