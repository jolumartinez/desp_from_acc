from dash import html
from components.layout import navbar  # Importamos el menú de navegación

def layout():
    return html.Div(
        className="container",
        children=[
            navbar(),  # Menú de navegación
            html.H1("Configuraciones"),
            html.P("Aquí puedes ajustar las configuraciones de la aplicación."),
        ]
    )
