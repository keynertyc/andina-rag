# Diseño de la aplicación

El plan aprobado define una consola operativa sencilla para un analista en escritorio,
con lectura frecuente bajo iluminación de oficina. Prioridad: revisar evidencia y tomar
decisiones sin distracciones. El patrón elegido es una mesa de revisión: lista a la
izquierda y detalle comparativo a la derecha; navegación por Guías, Lotes y Revisión.

- Superficies claras, texto azul profundo y acento verde petróleo; alertas por texto e icono,
  además de color. No se usan imágenes decorativas ni visualizaciones de datos inventados.
- Tipografía del sistema, cuerpo de 15–16 px y títulos con jerarquía breve.
- Controles nativos etiquetados, foco visible y objetivos de interacción de al menos 40 px.
- Espaciado base de 4 px; separación mayor entre tareas que entre etiqueta y campo.
- Tabla/lista y detalle se apilan en pantallas estrechas. Sin scroll horizontal de la página.
- Botones de revisión junto al contenido editable; citas en una sección persistente debajo.
- Estados explícitos de carga, vacío, error, bloqueo, guardado y desactualización.
- Movimiento limitado a estados de interacción y respetando prefers-reduced-motion.

Dirección fijada por el plan de implementación y su requisito de evitar complejidad extra.
