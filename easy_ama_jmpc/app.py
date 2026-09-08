import dash
from dash import html, dcc
from components.layout import create_layout
from pages import page1, page2, page3
from callbacks import app_callbacks  # Importamos los callbacks para la carga de archivos

# Inicializar la aplicación Dash
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Definimos el layout principal de la aplicación con navegación
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),  # Controla la URL para la navegación
    html.Div(id='page-content')  # Contenedor donde se cargan las diferentes páginas
])

# Callback para actualizar el contenido de la página según la URL
@app.callback(dash.dependencies.Output('page-content', 'children'),
              [dash.dependencies.Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/page1':
        return page1.layout()
    elif pathname == '/page2':
        return page2.layout()
    elif pathname == '/page3':
        return page3.layout()
    else:
        return create_layout()  # Página de inicio

# Registrar callbacks después de definir la instancia de `app`
app_callbacks.register_callbacks(app)

if __name__ == '__main__':
    app.run_server(debug=True, port=8051)
