# Precio Justo Agrícola
Prototipo académico del Grupo 4. Chat de campaña, pronóstico Random Forest y dashboard. No realiza ventas ni integra WhatsApp.

## Publicación
1. Crea un repositorio GitHub y sube el contenido de esta carpeta (app.py, logic.py, requirements.txt, modelo/ y opcionalmente .streamlit/config.toml y .gitignore).
2. En share.streamlit.io, crea una app, selecciona el repositorio, rama y app.py. Elige Python 3.12 en Advanced settings.
3. En Secrets agrega los valores siguientes con tus claves privadas. Nunca los publiques en GitHub.
```toml
GEMINI_API_KEY = "TU_CLAVE"
GEMINI_MODEL = "gemini-flash-latest"
ADMIN_PASSWORD = "TU_CLAVE_INTERNA_PRIVADA"
```
4. Deploy. Abre el enlace público, prueba el chat y el modelo. En Código QR pega la URL real y descarga el PNG.
5. Si Gemini no responde se muestra explícitamente el modo por reglas. Verifica cuota, clave y modelo en AI Studio.

## Prueba de extremo a extremo
- Enviar UVA; comprobar guía sin permiso. Enviar ACEPTO. Consultar con una frase libre y comprobar etiqueta Gemini. Registrar 2 kg. Desde Panel del equipo confirmar pedido de prueba. Verificar dashboard. Enviar SALIR y verificar retiro.
- Los contadores son sesiones de prueba, no personas únicas; SQLite local puede perderse en reinicios. No hay captura de datos identificativos, mensajes externos, integración WhatsApp ni secuencia real de días 1, 3 y 7. El sistema no recoge ventas reales. No usar para producción.
- El aviso informa que las consultas libres se envían a Gemini. No introducir datos personales. No almacenar claves en código. Revocar la clave cuando concluya la demo si corresponde y controlar cuota.

## Ejecución local opcional
Python 3.12, `pip install -r requirements.txt`, crear `.streamlit/secrets.toml` localmente y ejecutar `streamlit run app.py`.
