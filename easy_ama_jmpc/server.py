import dash

# Instancia de la aplicación Dash
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server  # Esto permite que Dash funcione en servidores de producción
