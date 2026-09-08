from dash import html, dcc
from components.layout import navbar  # Importamos el menú de navegación

def layout():
    return html.Div(
        className="container",
        children=[
            navbar(),  # Menú de navegación
            html.H1("Estadísticas"),
            html.Div(
                className="graph-container",
                children=[
                    dcc.Graph(id="statistics-graph"),
                    html.P("Visualiza las estadísticas de los datos."),
                ],
            ),
        ]
    )
