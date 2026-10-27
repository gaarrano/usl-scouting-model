# Lista corta permanente (Google Sheet)

Sin esto, la lista corta de la app online se borra cada vez que Streamlit reinicia la app.
Con una Google Sheet, queda guardada y la ven todos los que abren la app. Son unos 10 minutos, una sola vez.

1. **Crea la hoja.** En Google Drive, nueva hoja de cálculo. Nómbrala `MiamiFC_lista_corta`. Copia su URL.
2. **Crea una cuenta de servicio** (un "usuario robot" que escribe en la hoja):
   1. Entra a https://console.cloud.google.com y crea un proyecto (ej. `miamifc-scouting`).
   2. Menú → *APIs y servicios* → *Biblioteca*: habilita **Google Sheets API** y **Google Drive API**.
   3. Menú → *IAM y administración* → *Cuentas de servicio* → *Crear*. Nombre: `streamlit`. Sin roles. Crear.
   4. Abre la cuenta → pestaña *Claves* → *Agregar clave* → *JSON*. Se descarga un archivo `.json`.
3. **Comparte la hoja** con el correo de esa cuenta (está en el JSON, campo `client_email`, termina en
   `iam.gserviceaccount.com`), como **Editor**.
4. **Pega las credenciales en Streamlit.**
   - Online: share.streamlit.io → tu app → ⋮ → *Settings* → *Secrets*. Pega esto, reemplazando con los valores
     del JSON (el `private_key` va entre comillas, con los `\n` tal cual vienen):

     ```toml
     [gsheets]
     sheet_url = "https://docs.google.com/spreadsheets/d/XXXX/edit"

     [gsheets.service_account]
     type = "service_account"
     project_id = "miamifc-scouting"
     private_key_id = "..."
     private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
     client_email = "streamlit@miamifc-scouting.iam.gserviceaccount.com"
     client_id = "..."
     token_uri = "https://oauth2.googleapis.com/token"
     ```
   - En el Mac (opcional): el mismo texto en `.streamlit/secrets.toml` dentro del proyecto. Ese archivo NO se
     sube a git (está en .gitignore).
5. Reinicia la app. En *Lista corta* debe decir «Guardada en la Google Sheet del club».

El archivo JSON descargado es una llave: no lo subas al repo ni lo mandes por WhatsApp. Bórralo cuando lo hayas pegado.
